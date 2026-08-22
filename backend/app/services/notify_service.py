"""渠道通知（F3）：事件触发后按渠道订阅分发 webhook/邮件。

调用方式：路由层在事务提交成功后 `await notify(app, session, event, **ctx)`。
事件代码见 constants.NOTIFY_EVENTS；消息模板集中在本文件维护。
"""
import logging

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import NOTIFY_EVENTS
from app.core.timeutil import now
from app.models import NotificationChannel
from app.workers.dispatch import dispatch

logger = logging.getLogger(__name__)


def _build_message(event: str, ctx: dict) -> tuple[str, str]:
    """按事件组装 (标题, 正文)。正文为 markdown，行与行以换页符分隔。"""
    operator = ctx.get("operator", "")
    time_str = now().strftime("%Y-%m-%d %H:%M")
    lines = [f"时间：{time_str}"]
    if operator:
        lines.append(f"操作人：{operator}")
    if event == "vuln_created":
        title = "新漏洞创建"
        count = ctx.get("count")
        lines.append(f"漏洞：{ctx.get('title', '')}")
        if count is not None:
            lines.append(f"数量：{count} 个")
        if ctx.get("system"):
            lines.append(f"所属系统：{ctx['system']}")
    elif event == "plan_claimed":
        title = "测试工单认领"
        lines.append(f"工单系统：{ctx.get('system', '')}")
    elif event == "vuln_transition":
        title = "漏洞状态流转"
        lines.append(f"漏洞：{ctx.get('title', '')}")
        lines.append(f"流转：{ctx.get('from', '?')} → {ctx.get('to', '?')}")
    elif event == "retest_completed":
        title = "复测完成"
        lines.append(f"工单系统：{ctx.get('system', '')}")
        if ctx.get("report"):
            lines.append(f"复测报告：{ctx['report']}")
    else:
        title = NOTIFY_EVENTS.get(event, event)
        lines.extend(f"{k}：{v}" for k, v in ctx.items() if k not in ("operator",) and v)
    return f"[Talos] {title}", "\n".join(lines)


async def notify(app: FastAPI, session: AsyncSession, event: str, **ctx) -> None:
    """向订阅了 event 的活跃渠道分发通知（异步任务，尽力而为）。"""
    channels = (
        await session.execute(
            select(NotificationChannel).where(NotificationChannel.is_active.is_(True))
        )
    ).scalars().all()
    matched = [c for c in channels if event in (c.events or [])]
    if not matched:
        return
    title, body = _build_message(event, ctx)
    for channel in matched:
        await dispatch(app, "send_notify_task", channel.type, channel.config or {}, title, body)


async def send_test(app: FastAPI, channel: NotificationChannel) -> None:
    """渠道「测试发送」：固定文案验证连通性。"""
    title = "[Talos] 测试通知"
    body = f"这是一条测试通知，渠道「{channel.name}」配置成功。\n时间：{now().strftime('%Y-%m-%d %H:%M')}"
    await dispatch(app, "send_notify_task", channel.type, channel.config or {}, title, body)
