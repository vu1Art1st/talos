import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    ASSET_SEC_LEVEL,
    ASSET_STATUS,
    PERMISSIONS,
    TESTING_PLAN_STATUS,
    URL_TAG,
    VUL_LAYER,
    VUL_LEVEL,
    VUL_SOURCE,
    VUL_STATUS,
    VUL_TYPE,
)
from app.core.config import settings
from app.core.deps import get_current_user
from app.db import get_session
from app.models import Message, User

router = APIRouter(tags=["通用"])

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


@router.get("/meta")
async def meta(_: User = Depends(get_current_user)):
    """业务字典，前端下拉框统一从此获取。"""
    return {
        "vul_type": VUL_TYPE,
        "vul_level": VUL_LEVEL,
        "vul_status": VUL_STATUS,
        "vul_source": VUL_SOURCE,
        "vul_layer": VUL_LAYER,
        "asset_sec_level": ASSET_SEC_LEVEL,
        "asset_status": ASSET_STATUS,
        "url_tag": URL_TAG,
        "testing_plan_status": TESTING_PLAN_STATUS,
        "permissions": PERMISSIONS,
    }


@router.post("/upload/image")
async def upload_image(file: UploadFile, _: User = Depends(get_current_user)):
    """富文本编辑器图片上传。"""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"不支持的图片格式: {ext}")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "图片大小不能超过 10MB")
    name = f"{uuid.uuid4().hex}{ext}"
    (settings.storage_sub("uploads", "images") / name).write_bytes(data)
    return {"url": f"/storage/uploads/images/{name}"}


@router.get("/messages")
async def list_messages(
    unread_only: bool = False,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    cond = [Message.user_id == user.id]
    if unread_only:
        cond.append(Message.is_read.is_(False))
    rows = (
        await session.execute(
            select(Message).where(*cond).order_by(Message.id.desc()).limit(50)
        )
    ).scalars().all()
    return [
        {
            "id": m.id, "title": m.title, "content": m.content,
            "is_read": m.is_read, "create_time": m.create_time,
        }
        for m in rows
    ]


@router.post("/messages/read")
async def mark_read(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await session.execute(
        update(Message).where(Message.user_id == user.id).values(is_read=True)
    )
    await session.commit()
    return {"msg": "ok"}
