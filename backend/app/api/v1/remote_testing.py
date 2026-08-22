"""远程检测 API：通报口径的检测记录与申诉报告附件管理，统一 special:manage 权限。"""
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import require_perm
from app.core.query import get_or_404, paginate, apply_sort
from app.db import get_session
from app.models import RemoteTesting, User
from app.schemas import Page, RemoteTestingIn, RemoteTestingOut

router = APIRouter(tags=["专项管理"])


@router.get("/remote-testings", response_model=Page[RemoteTestingOut])
async def list_remote_testings(
    search: str = "",
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(
            RemoteTesting.system_name.ilike(f"%{search}%")
            | RemoteTesting.department.ilike(f"%{search}%")
            | RemoteTesting.notified_unit.ilike(f"%{search}%")
            | RemoteTesting.vuln_name.ilike(f"%{search}%")
        )
    stmt = select(RemoteTesting).where(*cond)
    stmt = apply_sort(
        stmt, RemoteTesting, sort, order,
        {"id", "system_name", "notice_time", "department", "is_external",
         "vuln_name", "appeal_status", "create_time"},
        RemoteTesting.id.desc(),
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=items)


# 申诉报告附件大小上限
MAX_APPEAL_FILE_BYTES = 20 * 1024 * 1024


@router.post("/remote-testings/upload-appeal")
async def upload_remote_appeal(
    file: UploadFile,
    _: User = Depends(require_perm("special:manage")),
):
    """上传远程检测-申诉报告附件（支持 Word/PDF/图片等），返回文件元信息供表单绑定。"""
    data = await file.read()
    if len(data) > MAX_APPEAL_FILE_BYTES:
        raise HTTPException(400, "申诉报告文件大小不能超过 20MB")
    if not data:
        raise HTTPException(400, "文件内容为空")
    ext = Path(file.filename or "").suffix.lower() or ".bin"
    name = f"{uuid.uuid4().hex}{ext}"
    path = settings.storage_sub("uploads", "remote_appeal") / name
    path.write_bytes(data)
    return {
        "name": file.filename or name,
        "path": str(Path("uploads", "remote_appeal") / name).replace("\\", "/"),
        "size": len(data),
    }


@router.post("/remote-testings", response_model=RemoteTestingOut)
async def create_remote_testing(
    body: RemoteTestingIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = RemoteTesting(**body.model_dump(), creator_id=user.id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.put("/remote-testings/{row_id}", response_model=RemoteTestingOut)
async def update_remote_testing(
    row_id: int,
    body: RemoteTestingIn,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, RemoteTesting, row_id, "远程检测记录不存在")
    old_path = row.appeal_file_path
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    await session.commit()
    # 替换附件时清理旧文件（更新失败时旧文件仍保留，不影响记录）
    if old_path and old_path != row.appeal_file_path:
        _remove_appeal_file(old_path)
    await session.refresh(row)
    return row


@router.get("/remote-testings/{row_id}/appeal")
async def download_remote_appeal(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """下载远程检测-申诉报告附件。"""
    row = await get_or_404(session, RemoteTesting, row_id, "远程检测记录不存在")
    if not row.appeal_file_path:
        raise HTTPException(404, "暂无申诉报告附件")
    path = settings.storage_path / row.appeal_file_path
    if not path.is_file():
        raise HTTPException(404, "申诉报告文件已被清理")
    filename = quote(row.appeal_file_name or "appeal")
    return FileResponse(
        path,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


def _remove_appeal_file(rel_path: str) -> None:
    """删除申诉报告附件（尽力而为，文件缺失时忽略）。"""
    try:
        (settings.storage_path / rel_path).unlink(missing_ok=True)
    except OSError:
        pass


@router.delete("/remote-testings/{row_id}")
async def delete_remote_testing(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(RemoteTesting, row_id)
    if row:
        if row.appeal_file_path:
            _remove_appeal_file(row.appeal_file_path)
        await session.delete(row)
        await session.commit()
    return {"msg": "删除成功"}
