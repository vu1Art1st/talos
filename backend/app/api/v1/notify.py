"""通知渠道管理（F3）：企业微信/钉钉 webhook 与邮件渠道的后台配置。"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.query import get_or_404, paginate
from app.db import get_session
from app.models import NotificationChannel, User
from app.schemas import NotifyChannelIn, NotifyChannelOut, Page
from app.services.audit_service import audit
from app.services.notify_service import send_test

router = APIRouter(prefix="/notify-channels", tags=["通知渠道"])


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


@router.post("/{channel_id}/test")
async def test_channel(
    channel_id: int,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    """发送测试通知验证渠道连通性（异步执行，返回即代表已入队）。"""
    row = await get_or_404(session, NotificationChannel, channel_id, "通知渠道不存在")
    await send_test(request.app, row)
    return {"msg": "测试通知已发送，请到对应渠道确认是否收到"}
