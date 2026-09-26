"""开放 API 写操作幂等（P1-6）。

口径（`Idempotency-Key` 请求头，仅作用于开放 API 的写接口）：

1. **抢占在前**：请求进入时先以 `(user_id, endpoint, key)` 尝试写入占位记录
   （`ON CONFLICT DO NOTHING`）。抢占成功 = 首次执行；抢占失败说明同键请求已存在：
   - 记录仍处于「处理中」（status_code=0）→ 409，提示稍后重试；
   - 记录已完成且**请求体哈希一致** → 原样返回首次结果（重放）；
   - 请求体哈希不一致 → 409，禁止同键改写不同内容。
2. **完成后回填**：业务成功后写入状态码与响应体，之后的重放直接命中。
3. 过期记录由 worker 的定期清理任务删除，避免无界增长。

这样即使客户端超时重试，也不会产生第二个工单（验收要求）。
"""
import hashlib
import json
import logging
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import now
from app.models import ApiIdempotencyKey

logger = logging.getLogger(__name__)

# 幂等记录保留期（天）：覆盖客户端重试窗口，之后可回收
RETENTION_DAYS = 7
_KEY_MAX = 120


def payload_hash(payload) -> str:
    """请求体哈希（排序键 + 紧凑 JSON），用于判断同键请求内容是否一致。"""
    try:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        text = str(payload)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _full_key(user_id: int, endpoint: str, key: str) -> str:
    return f"{user_id}:{endpoint}:{key}"[:_KEY_MAX * 2]


async def claim(
    session: AsyncSession, user_id: int, endpoint: str, key: str, payload,
) -> tuple[str, dict | None]:
    """抢占幂等键。

    返回 `(outcome, replay)`：
    - `("proceed", None)`：首次执行，调用方正常处理；
    - `("replay", {...})`：返回首次结果（status_code + response）；
    - `("conflict", None)`：同键不同内容，调用方应返回 409。
    """
    full = _full_key(user_id, endpoint, key)
    digest = payload_hash(payload)
    result = await session.execute(
        pg_insert(ApiIdempotencyKey)
        .values(
            key=full, user_id=user_id, endpoint=endpoint,
            payload_hash=digest, status_code=0, response="",
        )
        .on_conflict_do_nothing(index_elements=[ApiIdempotencyKey.key])
    )
    await session.commit()
    if result.rowcount == 1:
        return "proceed", None
    row = await session.get(ApiIdempotencyKey, full)
    if row is None:  # 极小概率：并发下刚被清理
        return "proceed", None
    if row.payload_hash != digest:
        return "conflict", None
    if not row.status_code:
        raise HTTPException(409, "同一 Idempotency-Key 的请求正在处理中，请稍后重试")
    try:
        body = json.loads(row.response or "{}")
    except ValueError:
        body = {}
    return "replay", {"status_code": row.status_code or 200, "response": body}


async def remember(
    session: AsyncSession, user_id: int, endpoint: str, key: str, status_code: int, response,
) -> None:
    """业务完成后回填幂等结果（独立提交，失败不影响业务）。"""
    full = _full_key(user_id, endpoint, key)
    try:
        row = await session.get(ApiIdempotencyKey, full)
        if row is None:
            return
        if hasattr(response, "model_dump"):
            body = response.model_dump(mode="json")
        elif hasattr(response, "dict"):
            body = response.dict()
        else:
            body = response if isinstance(response, dict) else {"result": str(response)}
        row.status_code = int(status_code)
        row.response = json.dumps(body, ensure_ascii=False, default=str)
        await session.commit()
    except Exception as exc:  # noqa: BLE001  幂等回填失败不应影响已成功的业务
        logger.warning("幂等结果回填失败 key=%s: %s", key, exc)
        await session.rollback()


def key_of(headers) -> str:
    """从请求头取幂等键（超长截断）。"""
    return (headers.get("Idempotency-Key") or "").strip()[:128]


async def cleanup(session: AsyncSession, days: int = RETENTION_DAYS) -> int:
    result = await session.execute(
        delete(ApiIdempotencyKey).where(
            ApiIdempotencyKey.create_time < now() - timedelta(days=days)
        )
    )
    return int(result.rowcount or 0)
