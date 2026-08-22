import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    ASSET_SEC_LEVEL,
    ASSET_STATUS,
    ASSET_STATUS_COLOR,
    EXPORT_JOB_STATUS_NAME,
    IMPORT_BATCH_STATUS_NAME,
    IMPORT_RECORD_STATUS_NAME,
    NONPEN_ITEM_ACTION_NAMES,
    NONPEN_ITEM_ACTIONS,
    NONPEN_ITEM_COLORS,
    NONPEN_ITEM_STATUS,
    NONPEN_ITEMS,
    PERMISSIONS,
    REPORT_STATUS_COLOR,
    REPORT_STATUS_NAME,
    TESTING_PLAN_STATUS,
    TESTING_PLAN_STATUS_COLOR,
    URL_TAG,
    URL_TAG_COLOR,
    VUL_LAYER,
    VUL_LEVEL,
    VUL_LEVEL_COLOR,
    VUL_SOURCE,
    VUL_STATUS,
    VUL_STATUS_COLOR,
    VUL_TYPE_COLOR,
)
from app.core.config import settings
from app.core.deps import get_current_user, require_perm
from app.db import get_session
from app.models import DictOption, Message, User, VulnType
from app.schemas import DictOptionIn, DictOptionOut, VulnTypeIn, VulnTypeOut

router = APIRouter(tags=["通用"])

ALLOWED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _is_allowed_image(data: bytes) -> bool:
    """校验图片文件头魔术字节，防止伪造扩展名的非图片文件入库。"""
    return (
        data.startswith(b"\x89PNG\r\n\x1a\n")            # png
        or data.startswith(b"\xff\xd8\xff")               # jpg/jpeg
        or data[:6] in (b"GIF87a", b"GIF89a")             # gif
        or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")  # webp
    )


@router.get("/meta")
async def meta(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """业务字典，前端下拉框与状态标签统一从此获取（名称 + 颜色 + nonpen 命名空间均在此单源下发）。

    漏洞类型从数据库读取，支持动态新增；colors 命名空间为各字典的展示色值，
    动态新增的漏洞类型（code≥1000）无内置色值，由前端兜底灰色。
    """
    vuln_types = (
        await session.execute(select(VulnType).order_by(VulnType.sort, VulnType.id))
    ).scalars().all()
    vul_type_dict = {vt.code: vt.name for vt in vuln_types}
    system_types = (
        await session.execute(
            select(DictOption).where(DictOption.category == "system_type")
            .order_by(DictOption.sort, DictOption.id)
        )
    ).scalars().all()
    system_type_list = [st.name for st in system_types]
    return {
        "vul_type": vul_type_dict,
        "vul_level": VUL_LEVEL,
        "vul_status": VUL_STATUS,
        "vul_source": VUL_SOURCE,
        "vul_layer": VUL_LAYER,
        "asset_sec_level": ASSET_SEC_LEVEL,
        "asset_status": ASSET_STATUS,
        "system_type": system_type_list,
        "url_tag": URL_TAG,
        "testing_plan_status": TESTING_PLAN_STATUS,
        "report_status": REPORT_STATUS_NAME,
        "import_batch_status": IMPORT_BATCH_STATUS_NAME,
        "import_record_status": IMPORT_RECORD_STATUS_NAME,
        "export_job_status": EXPORT_JOB_STATUS_NAME,
        "permissions": PERMISSIONS,
        # 各字典的展示色值（key 与上方名称字典一一对应）
        "colors": {
            "vul_level": VUL_LEVEL_COLOR,
            "vul_status": VUL_STATUS_COLOR,
            "vul_type": VUL_TYPE_COLOR,
            "testing_plan_status": TESTING_PLAN_STATUS_COLOR,
            "report_status": REPORT_STATUS_COLOR,
            "asset_status": ASSET_STATUS_COLOR,
            "url_tag": URL_TAG_COLOR,
            "nonpen_item": NONPEN_ITEM_COLORS,
        },
        # 漏扫基线工单：测试项 / 状态 / 允许操作（有序，即按钮渲染顺序）与操作文案
        "nonpen": {
            "items": [
                {"key": key, "name": name, "desc": desc}
                for key, (name, desc) in NONPEN_ITEMS.items()
            ],
            "status": NONPEN_ITEM_STATUS,
            "actions": {status: list(actions) for status, actions in NONPEN_ITEM_ACTIONS.items()},
            "action_names": NONPEN_ITEM_ACTION_NAMES,
        },
    }


@router.get("/dict/{category}", response_model=list[DictOptionOut])
async def list_dict_options(
    category: str,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """可维护业务字典（如测试计划-测试类型 test_type），登录用户可读。"""
    return (
        await session.execute(
            select(DictOption).where(DictOption.category == category)
            .order_by(DictOption.sort, DictOption.id)
        )
    ).scalars().all()


@router.post("/dict/{category}", response_model=DictOptionOut)
async def create_dict_option(
    category: str,
    body: DictOptionIn,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """下拉框「新增」入口：新选项持久化，供后续复用。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "选项名称不能为空")
    exists = (
        await session.execute(
            select(DictOption).where(DictOption.category == category, DictOption.name == name)
        )
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(400, "同名选项已存在")
    row = DictOption(category=category, name=name, sort=body.sort)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


# ---------- 漏洞类型字典 ----------
@router.get("/vuln-types", response_model=list[VulnTypeOut])
async def list_vuln_types(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """漏洞类型列表（登录用户可读），/meta 已合并返回 {code: name}。"""
    return (
        await session.execute(select(VulnType).order_by(VulnType.sort, VulnType.id))
    ).scalars().all()


@router.post("/vuln-types", response_model=VulnTypeOut)
async def create_vuln_type(
    body: VulnTypeIn,
    _: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """新增自定义漏洞类型。code 从 1000 起递增，与内置编码空间分离避免冲突。"""
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "类型名称不能为空")
    exists = (
        await session.execute(select(VulnType).where(VulnType.name == name))
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(400, "同名漏洞类型已存在")
    max_code = (
        await session.execute(select(func.max(VulnType.code)))
    ).scalar_one()
    code = max(max_code or 75, 999) + 1
    row = VulnType(code=code, name=name, sort=body.sort, is_builtin=False)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/vuln-types/{type_id}")
async def delete_vuln_type(
    type_id: int,
    _: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """删除漏洞类型：内置类型不可删除。"""
    row = await session.get(VulnType, type_id)
    if row is None:
        raise HTTPException(404, "漏洞类型不存在")
    if row.is_builtin:
        raise HTTPException(400, "内置漏洞类型不可删除")
    await session.delete(row)
    await session.commit()
    return {"msg": "删除成功"}


@router.post("/upload/image")
async def upload_image(file: UploadFile, _: User = Depends(get_current_user)):
    """富文本编辑器图片上传。"""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXT:
        raise HTTPException(400, f"不支持的图片格式: {ext}")
    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, "图片大小不能超过 10MB")
    if not _is_allowed_image(data):
        raise HTTPException(400, "文件内容不是有效的图片")
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
