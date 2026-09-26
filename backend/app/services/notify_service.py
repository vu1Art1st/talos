"""渠道通知（F3 + P1-3 投递可观测与失败恢复）。

调用方式：路由层在事务提交成功后 `await notify(app, session, event, **ctx)`；
事件代码见 `constants.NOTIFY_EVENTS`，消息模板集中在本文件维护。

P1-3 改造要点：
1. **每条投递落库**（`NotifyDelivery`）：渠道、事件、目标摘要、请求时间、状态码、
   尝试次数、最后错误、下次重试时间、死信原因；进程重启不丢失待重试记录。
2. **失败恢复**：可重试错误按指数退避写入 `next_retry_at`，由 worker 的 cron
   `retry_deliveries_task` 重新投递；永久错误或超过最大尝试次数进死信。
3. **结果回执**：测试发送同步执行并返回实际结果（不再只返回「已入队」）。
4. 出站前再次做 SSRF 校验、禁用重定向、错误信息脱敏（不泄露密钥与内网地址）。
"""
import asyncio
import logging
import smtplib
from datetime import timedelta
from email.header import Header
from email.mime.text import MIMEText
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import NOTIFY_EVENTS
from app.core.config import settings
from app.core.outbound import assert_public_url
from app.core.timeutil import now
from app.models import NotificationChannel, NotifyDelivery
from app.services import task_lifecycle
from app.workers.dispatch import dispatch

logger = logging.getLogger(__name__)

# 错误信息最大长度（避免把整段 HTML 错误页写进库）
_ERROR_MAX = 500


def _build_message(event: str, ctx: dict) -> tuple[str, str]:
    """按事件组装 (标题, 正文)。正文为 markdown，行与行以换行分隔。"""
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
    elif event in ("sla_due_soon", "sla_overdue"):
        title = NOTIFY_EVENTS[event]
        lines.append(f"漏洞：{ctx.get('title', '')}")
        if ctx.get("due_at"):
            lines.append(f"修复截止：{ctx['due_at']}")
        if event == "sla_overdue" and ctx.get("overdue_days") is not None:
            lines.append(f"已逾期：{ctx['overdue_days']} 天")
        if ctx.get("system"):
            lines.append(f"所属系统：{ctx['system']}")
    else:
        title = NOTIFY_EVENTS.get(event, event)
        lines.extend(f"{k}：{v}" for k, v in ctx.items() if k not in ("operator",) and v)
    return f"[Talos] {title}", "\n".join(lines)


def target_summary(channel_type: str, config: dict) -> str:
    """目标摘要（脱敏）：webhook 只留主机名，邮件只留域名。"""
    config = config or {}
    if channel_type == "email":
        domains = []
        for addr in config.get("recipients") or []:
            domain = str(addr).split("@")[-1] if "@" in str(addr) else ""
            if domain and domain not in domains:
                domains.append(domain)
        return f"{len(config.get('recipients') or [])} 个收件人（{'、'.join(domains[:3])}）"
    url = str(config.get("url") or "")
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        host = ""
    return host or "未配置"


def _sanitize_error(exc: BaseException, config: dict) -> str:
    """错误脱敏：去掉 webhook URL（含 access_token）与收件人明细，保留可操作信息。"""
    text = f"{type(exc).__name__}: {exc}"
    url = str((config or {}).get("url") or "")
    if url:
        text = text.replace(url, target_summary("wecom", config))
    for addr in (config or {}).get("recipients") or []:
        text = text.replace(str(addr), "***")
    return text[:_ERROR_MAX]


def _classify(channel_type: str, status_code: int, exc: BaseException | None) -> tuple[bool, str]:
    """判断失败是否可重试，并给出可操作错误文案。

    - 网络/超时/5xx/429：可重试（SMTP、DNS、TLS 超时属临时故障）；
    - 4xx（配置错误，如 webhook 地址无效、鉴权失败）：不可重试；
    - SSRF 校验拒绝 / 渠道删除：不可重试。
    """
    if exc is not None:
        if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
                            httpx.WriteTimeout, httpx.PoolTimeout, httpx.RemoteProtocolError)):
            return True, f"网络连接失败：{exc}"
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            return True, f"请求超时：{exc}"
        if isinstance(exc, smtplib.SMTPException):
            return True, f"SMTP 发送失败：{exc}"
        if isinstance(exc, OSError):
            return True, f"网络/系统错误：{exc}"
        return False, f"{type(exc).__name__}: {exc}"
    if status_code == 429 or status_code >= 500:
        return True, f"对端返回 {status_code}（服务暂时不可用，将退避重试）"
    if status_code >= 400:
        return False, f"对端返回 {status_code}（请检查渠道配置：地址、鉴权或收件人）"
    return False, ""


def _send_mail_sync(to: list[str], subject: str, body: str) -> None:
    if not settings.SMTP_HOST or not to:
        raise smtplib.SMTPException("未配置 SMTP 服务或收件人为空")
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = ",".join(to)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASS)
        server.sendmail(msg["From"], to, msg.as_string())


async def perform_send(channel_type: str, config: dict, title: str, body: str) -> tuple[int, str]:
    """实际执行一次外发，返回 `(http_status, error)`；error 为空表示成功。

    唯一实现：worker 任务与「测试发送」同步回执共用，避免两处发送逻辑分叉。
    """
    config = config or {}
    if channel_type in ("wecom", "dingtalk"):
        url = config.get("url") or ""
        if not url:
            return 0, "未配置 webhook 地址"
        try:
            url = assert_public_url(url, field="webhook 地址")
        except ValueError as exc:
            return 0, f"webhook 目标被拒绝（SSRF 防护）：{exc}"
        if channel_type == "wecom":
            payload = {"msgtype": "markdown", "markdown": {"content": f"**{title}**\n{body}"}}
        else:
            payload = {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": f"#### {title}\n\n{body}"},
            }
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                resp = await client.post(url, json=payload)
        except Exception as exc:  # noqa: BLE001  由 _classify 判定可重试性
            retryable, reason = _classify(channel_type, 0, exc)
            return 0, ("[可重试] " if retryable else "") + _sanitize_error(Exception(reason), config)
        if resp.status_code != 200:
            retryable, reason = _classify(channel_type, resp.status_code, None)
            return resp.status_code, ("[可重试] " if retryable else "") + reason
        return 200, ""
    if channel_type == "email":
        recipients = config.get("recipients") or []
        if not recipients:
            return 0, "未配置收件人"
        html = f"<p><strong>{title}</strong></p>" + "".join(
            f"<p>{line}</p>" for line in body.splitlines() if line.strip()
        )
        try:
            await asyncio.to_thread(_send_mail_sync, recipients, title, html)
        except Exception as exc:  # noqa: BLE001
            retryable, reason = _classify(channel_type, 0, exc)
            return 0, ("[可重试] " if retryable else "") + _sanitize_error(Exception(reason), config)
        return 200, ""
    return 0, f"不支持的通知渠道类型：{channel_type}"


def error_is_retryable(error: str) -> bool:
    """投递错误是否可重试（由 `perform_send` 的 `[可重试]` 前缀标记）。"""
    return error.startswith("[可重试]")


def _clean_error(error: str) -> str:
    return error.removeprefix("[可重试]").strip()


def _mark_dead(delivery: NotifyDelivery, reason: str) -> None:
    """进入死信：状态置 dead 并保留原因（不复用 task_lifecycle，字段口径不同）。"""
    delivery.status = "dead"
    delivery.last_error = _clean_error(reason) or delivery.last_error
    delivery.dead_letter_reason = _clean_error(reason) or "投递失败"
    delivery.next_retry_at = None
    delivery.finish_time = now()


# ---------- 投递记录 ----------
def _new_delivery(channel: NotificationChannel, event: str, title: str, body: str) -> NotifyDelivery:
    return NotifyDelivery(
        channel_id=channel.id, channel_name=channel.name, channel_type=channel.type,
        event=event, title=title[:255], content=body,
        target=target_summary(channel.type, channel.config or {}),
        status="pending", request_time=now(),
    )


async def notify(app: FastAPI, session: AsyncSession, event: str, **ctx) -> list[NotifyDelivery]:
    """向订阅了 event 的活跃渠道分发通知，并为每条投递建立记录。"""
    channels = (
        await session.execute(
            select(NotificationChannel).where(NotificationChannel.is_active.is_(True))
        )
    ).scalars().all()
    matched = [c for c in channels if event in (c.events or [])]
    if not matched:
        return []
    title, body = _build_message(event, ctx)
    deliveries = []
    for channel in matched:
        row = _new_delivery(channel, event, title, body)
        session.add(row)
        deliveries.append(row)
    # 先落库拿到 id：任务参数用「投递记录 id」，重试与观测都以它为准。
    # 必须**提交**再投递：调用方约定在业务事务提交后调用本函数，而「无队列」形态下任务会在
    # 当前进程内立即执行，未提交的行对任务不可见（历史缺陷：投递记录随请求 session 关闭被回滚）。
    await session.flush()
    await session.commit()
    for row in deliveries:
        await dispatch(app, "send_notify_task", row.id, job_id=f"notify:{row.id}")
    return deliveries


async def _reload_channel(session: AsyncSession, delivery: NotifyDelivery) -> NotificationChannel | None:
    if delivery.channel_id is None:
        return None
    return await session.get(NotificationChannel, delivery.channel_id)


async def notify_inline(session: AsyncSession, event: str, **ctx) -> int:
    """worker 侧（无 FastAPI app）投递：创建记录并立即执行，返回投递条数。

    与 `notify()` 共用事件匹配与消息组装；区别只是不经过 arq（worker 内没有 app.state.arq）。
    """
    channels = (
        await session.execute(
            select(NotificationChannel).where(NotificationChannel.is_active.is_(True))
        )
    ).scalars().all()
    matched = [c for c in channels if event in (c.events or [])]
    if not matched:
        return 0
    title, body = _build_message(event, ctx)
    for channel in matched:
        row = _new_delivery(channel, event, title, body)
        session.add(row)
        await session.flush()
        await send_delivery(session, row)
    return len(matched)


async def cleanup_deliveries(session: AsyncSession, days: int = 30) -> int:
    """清理保留期之外的终态投递记录（success/dead），避免无界增长。"""
    from sqlalchemy import delete

    cutoff = now() - timedelta(days=days)
    result = await session.execute(
        delete(NotifyDelivery).where(
            NotifyDelivery.status.in_(("success", "dead")),
            NotifyDelivery.request_time < cutoff,
        )
    )
    return int(result.rowcount or 0)


async def send_delivery(session: AsyncSession, delivery: NotifyDelivery, *, manual: bool = False) -> None:
    """投递单条记录：更新状态、尝试次数、错误与重试计划（worker 与重放共用）。

    失败时**不抛异常**：重试由 `next_retry_at` + worker cron 驱动，
    这样重试状态可查询、进程重启不丢失，也不会与 arq 自身重试叠加。
    """
    channel = await _reload_channel(session, delivery)
    if channel is None:
        _mark_dead(delivery, "通知渠道已被删除")
        return
    delivery.attempts = int(delivery.attempts or 0) + 1
    delivery.last_attempt_at = now()
    status_code, error = await perform_send(
        channel.type, channel.config or {}, delivery.title, delivery.content,
    )
    delivery.http_status = status_code
    if not error:
        delivery.status = "success"
        delivery.last_error = ""
        delivery.next_retry_at = None
        delivery.dead_letter_reason = ""
        delivery.finish_time = now()
        return
    clean = _clean_error(error)
    with_attempts = max(int(getattr(delivery, "attempts", 0) or 0), 1)
    if not error_is_retryable(error) or with_attempts >= max(settings.TASK_MAX_ATTEMPTS, 1):
        _mark_dead(delivery, clean)
        return
    delivery.status = "failed"
    delivery.last_error = clean
    delivery.dead_letter_reason = ""
    delivery.next_retry_at = now() + timedelta(seconds=task_lifecycle.backoff_seconds(with_attempts))


async def send_test(app: FastAPI, session: AsyncSession, channel: NotificationChannel) -> NotifyDelivery:
    """渠道「测试发送」：**同步执行**并返回实际结果回执（不再只返回「已入队」）。"""
    title = "[Talos] 测试通知"
    body = (
        f"这是一条测试通知，渠道「{channel.name}」配置成功。\n"
        f"时间：{now().strftime('%Y-%m-%d %H:%M')}"
    )
    row = _new_delivery(channel, "test", title, body)
    session.add(row)
    await session.flush()
    await send_delivery(session, row, manual=True)
    await session.commit()
    await session.refresh(row)
    return row


async def replay_delivery(
    app: FastAPI, session: AsyncSession, delivery: NotifyDelivery,
) -> NotifyDelivery:
    """重放单条失败 / 死信投递：重置状态后立即重新投递。"""
    delivery.status = "pending"
    delivery.attempts = 0
    delivery.last_error = ""
    delivery.dead_letter_reason = ""
    delivery.next_retry_at = None
    delivery.finish_time = None
    await session.flush()
    await send_delivery(session, delivery)
    await session.commit()
    await session.refresh(delivery)
    return delivery


async def retry_due_deliveries(session: AsyncSession, limit: int = 100) -> int:
    """重投到期的失败投递（worker cron 调用）；返回处理条数。"""
    rows = (
        await session.execute(
            select(NotifyDelivery)
            .where(
                NotifyDelivery.status == "failed",
                NotifyDelivery.next_retry_at.is_not(None),
                NotifyDelivery.next_retry_at <= now(),
            )
            .order_by(NotifyDelivery.next_retry_at)
            .limit(limit)
        )
    ).scalars().all()
    for row in rows:
        await send_delivery(session, row)
    return len(rows)
