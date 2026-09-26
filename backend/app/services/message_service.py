"""站内消息统一写入（P1-2）。

**为什么需要**：此前站内信由三处路由各自 `session.add(Message(...))` 直写，没有统一
入口、没有深链、没有失效保护。本模块收敛为 `create_message()`：

- 所有事件（漏洞流转、工单认领、复测、导入、SLA、报告）统一经此写入；
- `dedup_key` 非空时借助 `task_dedup` 抢占幂等键，避免同一事件重复通知；
- **失败不影响主业务事务**：写入包在 SAVEPOINT 中，异常时回滚到保存点并记录告警，
  调用方继续提交其余业务数据（「消息生成失败不影响主业务事务，但必须记录告警」）。

权限：`link` 只是站内深链，前端在权限不足时跳无权限页，消息正文不携带敏感内容。
"""
import logging
from datetime import timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import MESSAGE_TYPES
from app.core.timeutil import now
from app.models import Message
from app.services import task_dedup

logger = logging.getLogger(__name__)

# 消息保留期（P1-2）：已读 90 天、未读 180 天；避免无界增长
RETENTION_READ_DAYS = 90
RETENTION_UNREAD_DAYS = 180


async def create_message(
    session: AsyncSession,
    user_id: int | None,
    msg_type: str,
    title: str,
    content: str = "",
    *,
    link: str = "",
    dedup_key: str = "",
    commit: bool = False,
) -> Message | None:
    """写入一条站内消息；失败仅告警并返回 None（不抛异常、不污染主事务）。

    `commit=True` 时在写入后立即提交（用于「事件已提交、消息随后补发」的旁路场景）；
    默认跟随调用方事务。
    """
    if not user_id:
        return None
    if msg_type not in MESSAGE_TYPES:
        msg_type = "system"
    try:
        async with session.begin_nested():
            if dedup_key and not await task_dedup.claim_dedup_key(session, dedup_key):
                return None
            row = Message(
                user_id=int(user_id), msg_type=msg_type, title=(title or "")[:255],
                content=content or "", link=(link or "")[:255],
            )
            session.add(row)
        if commit:
            await session.commit()
        return row
    except Exception as exc:  # noqa: BLE001  消息失败不得阻断主业务
        logger.warning("站内消息写入失败（不影响主业务）user=%s type=%s: %s", user_id, msg_type, exc)
        return None


async def cleanup_messages(session: AsyncSession) -> int:
    """按保留期清理消息：已读超 90 天、未读超 180 天；返回删除条数。

    保留期口径集中在此（worker 的每日清理任务调用），避免各处自行决定。
    """
    cutoff_read = now() - timedelta(days=RETENTION_READ_DAYS)
    cutoff_unread = now() - timedelta(days=RETENTION_UNREAD_DAYS)
    result = await session.execute(
        delete(Message).where(
            (Message.is_read.is_(True) & (Message.create_time < cutoff_read))
            | (Message.is_read.is_(False) & (Message.create_time < cutoff_unread))
        )
    )
    return int(result.rowcount or 0)


async def create_messages(
    session: AsyncSession,
    user_ids: list[int],
    msg_type: str,
    title: str,
    content: str = "",
    *,
    link: str = "",
    dedup_key: str = "",
) -> int:
    """批量写入（自动去重 user_ids）；返回成功写入条数。"""
    seen: set[int] = set()
    count = 0
    for uid in user_ids:
        if not uid or uid in seen:
            continue
        seen.add(uid)
        key = f"{dedup_key}:{uid}" if dedup_key else ""
        if await create_message(
            session, uid, msg_type, title, content, link=link, dedup_key=key,
        ) is not None:
            count += 1
    return count
