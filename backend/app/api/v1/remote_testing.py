"""远程检测 API：通报口径的检测记录与申诉报告附件管理，统一 special:manage 权限。"""
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import require_perm
from app.core.query import get_or_404, paginate, apply_sort
from app.db import get_session
from app.models import Asset, RemoteTesting, User, Vul
from app.schemas import Page, RemoteTestingIn, RemoteTestingOut
from app.services import vuln_service
from app.services.upload_store import save_upload

logger = logging.getLogger(__name__)

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
    stmt = select(RemoteTesting)
    if search:
        like = f"%{search}%"
        # 关联漏洞的标题同样参与检索（旧记录的文本快照仍保留匹配）
        stmt = stmt.outerjoin(Vul, RemoteTesting.vuln_id == Vul.id).where(
            RemoteTesting.system_name.ilike(like)
            | RemoteTesting.department.ilike(like)
            | RemoteTesting.asset_belong.ilike(like)
            | RemoteTesting.notified_unit.ilike(like)
            | RemoteTesting.vuln_name.ilike(like)
            | Vul.title.ilike(like)
        )
    stmt = apply_sort(
        stmt, RemoteTesting, sort, order,
        {"id", "system_name", "notice_time", "department", "asset_belong", "is_external",
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
    original_name, rel_path, size = await save_upload(
        file,
        "remote_appeal",
        max_bytes=MAX_APPEAL_FILE_BYTES,
        size_error="申诉报告文件大小不能超过 20MB",
    )
    return {"name": original_name, "path": rel_path, "size": size}


async def _resolve_links(
    session: AsyncSession, body: RemoteTestingIn, user: User,
) -> dict:
    """解析远程检测的关联资产与关联漏洞。

    - asset_id 非空时校验资产存在；
    - new_vul 非空时创建漏洞（来源取草稿自带的 VUL_SOURCE），回填 vuln_id；
    - 最终存在关联漏洞时，以漏洞标题/类型同步文本快照，保证列表与导出口径一致。
    """
    data = body.model_dump(exclude={"new_vul"})
    if body.asset_id and not await session.get(Asset, body.asset_id):
        raise HTTPException(400, "关联资产不存在")
    vul: Vul | None = None
    if body.new_vul:
        created = await vuln_service.create_draft_vulns(
            session, [body.new_vul], user, body.new_vul.source,
        )
        vul = created[0]
        data["vuln_id"] = vul.id
    elif body.vuln_id:
        vul = await session.get(Vul, body.vuln_id)
        if not vul:
            raise HTTPException(400, "关联漏洞不存在")
    if vul is not None:
        data["vuln_name"] = vul.title
        data["vuln_type"] = str(vul.vul_type)
    return data


@router.post("/remote-testings", response_model=RemoteTestingOut)
async def create_remote_testing(
    body: RemoteTestingIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    data = await _resolve_links(session, body, user)
    row = RemoteTesting(**data, creator_id=user.id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.put("/remote-testings/{row_id}", response_model=RemoteTestingOut)
async def update_remote_testing(
    row_id: int,
    body: RemoteTestingIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, RemoteTesting, row_id, "远程检测记录不存在")
    old_path = row.appeal_file_path
    for k, v in (await _resolve_links(session, body, user)).items():
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
    except OSError as exc:
        # 尽力而为：文件被占用/无权限时仅记录，不阻断删除流程
        logger.warning("删除申诉报告附件失败 path=%s: %s", rel_path, exc)


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
