"""通知渠道管理（F3）与投递记录（P1-3 可观测与失败恢复）。"""
from datetime import timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.query import get_or_404, paginate
from app.core.timeutil import parse_date
from app.db import get_session
from app.models import NotificationChannel, NotifyDelivery, User
from app.schemas import (
    NotifyChannelIn,
    NotifyChannelOut,
    NotifyDeliveryOut,
    NotifyTestOut,
    Page,
)
from app.services import notify_service
from app.services.audit_service import audit

router = APIRouter(prefix="/notify-channels", tags=["通知渠道"])


# ---------- 投递记录（P1-3） ----------
@router.get("/deliveries", response_model=Page[NotifyDeliveryOut])
async def list_deliveries(
    channel_id: int | None = None,
    event: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    """投递记录查询：按渠道 / 事件 / 状态 / 时间（请求时间，半开区间）筛选。"""
    cond = []
    if channel_id is not None:
        cond.append(NotifyDelivery.channel_id == channel_id)
    if event:
        cond.append(NotifyDelivery.event == event)
    if status:
        cond.append(NotifyDelivery.status == status)
    # DateTime 列按「天」过滤：用 [当日 00:00, 次日 00:00) 半开区间，
    # 禁止 func.date(col) >= '日期串'（PostgreSQL 无该算子，会 500）
    start = parse_date(date_from)
    if start is not None:
        cond.append(NotifyDelivery.request_time >= start)
    end = parse_date(date_to)
    if end is not None:
        cond.append(NotifyDelivery.request_time < end + timedelta(days=1))
    total, items = await paginate(
        session,
        select(NotifyDelivery).where(*cond).order_by(NotifyDelivery.id.desc()),
        page, size,
    )
    return Page(total=total, items=[NotifyDeliveryOut.model_validate(i) for i in items])


@router.post("/deliveries/{delivery_id}/replay", response_model=NotifyDeliveryOut)
async def replay_delivery(
    delivery_id: int,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    """重放单条失败 / 死信投递（重置尝试次数后立即重投，返回最新状态）。"""
    row = await get_or_404(session, NotifyDelivery, delivery_id, "投递记录不存在")
    row = await notify_service.replay_delivery(request.app, session, row)
    await audit(session, request, "notify_delivery_replay", operator, {
        "delivery_id": delivery_id, "status": row.status,
    })
    return row


# ---------- 渠道管理 ----------
@router.get("", response_model=Page[NotifyChannelOut])
async def list_channels(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    total, items = await paginate(
        session, select(NotificationChannel).order_by(NotificationChannel.id.desc()), page, size,
    )
    return Page(total=total, items=[NotifyChannelOut.model_validate(i) for i in items])


@router.post("", response_model=NotifyChannelOut)
async def create_channel(
    body: NotifyChannelIn,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = NotificationChannel(
        name=body.name.strip(), type=body.type, config=body.config,
        events=body.events, is_active=body.is_active,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "notify_update", operator, {"op": "create", "name": row.name})
    return row


@router.put("/{channel_id}", response_model=NotifyChannelOut)
async def update_channel(
    channel_id: int,
    body: NotifyChannelIn,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, NotificationChannel, channel_id, "通知渠道不存在")
    row.name = body.name.strip()
    row.type = body.type
    row.config = body.config
    row.events = body.events
    row.is_active = body.is_active
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "notify_update", operator, {"op": "update", "name": row.name})
    return row


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: int,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(NotificationChannel, channel_id)
    if row:
        name = row.name
        await session.delete(row)
        await session.commit()
        await audit(session, request, "notify_update", operator, {"op": "delete", "name": name})
    return {"msg": "删除成功"}


async def _set_channel_active(
    session: AsyncSession, channel_id: int, active: bool,
) -> NotificationChannel:
    row = await get_or_404(session, NotificationChannel, channel_id, "通知渠道不存在")
    row.is_active = active
    await session.flush()
    return row


@router.post("/{channel_id}/pause", response_model=NotifyChannelOut)
async def pause_channel(
    channel_id: int,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    """暂停渠道：暂停后不再产生新投递（存量待重试记录仍可手动重放）。"""
    row = await _set_channel_active(session, channel_id, False)
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "notify_update", operator, {"op": "pause", "name": row.name})
    return row


@router.post("/{channel_id}/resume", response_model=NotifyChannelOut)
async def resume_channel(
    channel_id: int,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await _set_channel_active(session, channel_id, True)
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "notify_update", operator, {"op": "resume", "name": row.name})
    return row


@router.post("/{channel_id}/test", response_model=NotifyTestOut)
async def test_channel(
    channel_id: int,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    """测试发送：**同步执行**并返回实际结果回执（不再是「已入队」）。"""
    row = await get_or_404(session, NotificationChannel, channel_id, "通知渠道不存在")
    delivery = await notify_service.send_test(request.app, session, row)
    ok = delivery.status == "success"
    return NotifyTestOut(
        delivery_id=delivery.id,
        status=delivery.status,
        http_status=delivery.http_status,
        error=delivery.last_error if not ok else "",
        msg="测试通知已送达" if ok else f"测试通知发送失败：{delivery.last_error or '未知错误'}",
    )
