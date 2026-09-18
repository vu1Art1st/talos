"""春耕行动 API：记录 CRUD 与漏洞关联，统一 special:manage 权限。"""
import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import require_perm
from app.core.query import get_or_404, paginate, apply_sort
from app.core.storage import require_attachment_path, resolve_storage_path
from app.db import get_session
from app.models import SpringAction, User
from app.schemas import (
    Page,
    SpringActionIn,
    SpringActionOut,
    SpringActionVulDraft,
    SpringReportParseOut,
)
from app.services import vul_service
from app.services.audit_service import audit
from app.services.docx_parser import parse_any_docx
from app.services.upload_store import save_upload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["专项管理"])

# 原始报告附件大小上限与来源口径（VUL_SOURCE 中「春耕行动」）
MAX_REPORT_FILE_BYTES = 50 * 1024 * 1024
SPRING_VUL_SOURCE = 20
# 附件子目录：与 upload_spring_report 的 save_upload 参数一致，供路径白名单限定
REPORT_SUBDIR = "spring_report"


def _safe_report_path(raw: str) -> str:
    """写入侧附件路径白名单（审计 TALOS-2026-001/002）：仅接受本系统上传产物。"""
    return require_attachment_path(raw, subdir=REPORT_SUBDIR)


@router.get("/spring-actions", response_model=Page[SpringActionOut])
async def list_spring_actions(
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
            SpringAction.report_no.ilike(f"%{search}%")
            | SpringAction.system_name.ilike(f"%{search}%")
            | SpringAction.doc_no.ilike(f"%{search}%")
        )
    stmt = select(SpringAction).where(*cond)
    stmt = apply_sort(
        stmt, SpringAction, sort, order,
        {"id", "report_no", "system_name", "year", "phase", "asset_reason", "appeal_success",
         "est_score_deduction", "score_deduction", "doc_no", "create_time"},
        SpringAction.id.desc(),
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=items)


@router.post("/spring-actions/upload-report", response_model=SpringReportParseOut)
async def upload_spring_report(
    file: UploadFile,
    _: User = Depends(require_perm("special:manage")),
):
    """上传春耕行动-原始报告 Word 附件：存储留档并解析出系统名称/报告日期/漏洞草稿。

    兼容平台报告格式与固定导入模板格式（parse_any_docx 自动识别），
    漏洞草稿不落库，由前端勾选后随记录保存时创建并关联。
    """
    original_name, rel_path, size = await save_upload(
        file,
        "spring_report",
        max_bytes=MAX_REPORT_FILE_BYTES,
        require_ext=".docx",
        magic=b"PK\x03\x04",  # .docx 本质是 ZIP 包（与导入模块同一魔术字节校验）
        magic_error="文件不是有效的 .docx 文档",
        size_error="原始报告文件大小不能超过 50MB",
    )
    try:
        doc_kind, meta, records = parse_any_docx(
            str(settings.storage_path / rel_path),
            str(settings.storage_sub("uploads", "images")),
            "/storage/uploads/images",
            filename=original_name,
        )
    except Exception as exc:
        # 对外统一 400 文案，同时保留堆栈，便于区分「用户文件不可解析」与「服务端缺陷」（审计 C-3）
        logger.exception("春耕行动报告解析失败 file=%s", original_name)
        _remove_report_file(rel_path)
        raise HTTPException(400, "解析失败，请确认上传的是有效的 Word 文档") from exc
    meta = meta or {}  # 固定模板格式无封面元信息（system_name/报告日期为空）
    return SpringReportParseOut(
        name=original_name,
        path=rel_path,
        size=size,
        system_name=meta.get("system_name", ""),
        report_date=meta.get("report_date", ""),
        vuls=[
            SpringActionVulDraft(**{k: r[k] for k in SpringActionVulDraft.model_fields})
            for r in records if r.get("title")  # 模板格式标题为空的残缺记录不入草稿
        ],
    )


@router.post("/spring-actions", response_model=SpringActionOut)
async def create_spring_action(
    body: SpringActionIn,
    request: Request,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    data = body.model_dump(exclude={"vul_ids", "new_vuls"})
    data["report_file_path"] = _safe_report_path(data.get("report_file_path", ""))
    row = SpringAction(**data, creator_id=user.id)
    row.vuls = await vul_service.load_vulns_or_400(session, body.vul_ids)
    new_vuls = await vul_service.create_draft_vulns(session, body.new_vuls, user, SPRING_VUL_SOURCE)
    if new_vuls:
        row.vuls = list(row.vuls) + new_vuls
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "spring_action_change", user, {
        "op": "create", "target": f"spring-actions/{row.id}", "report_no": row.report_no,
    })
    return row


@router.put("/spring-actions/{row_id}", response_model=SpringActionOut)
async def update_spring_action(
    row_id: int,
    body: SpringActionIn,
    request: Request,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, SpringAction, row_id, "春耕行动记录不存在")
    old_path = row.report_file_path
    data = body.model_dump(exclude={"vul_ids", "new_vuls"})
    data["report_file_path"] = _safe_report_path(data.get("report_file_path", ""))
    for k, v in data.items():
        setattr(row, k, v)
    row.vuls = await vul_service.load_vulns_or_400(session, body.vul_ids)
    new_vuls = await vul_service.create_draft_vulns(session, body.new_vuls, user, SPRING_VUL_SOURCE)
    if new_vuls:
        row.vuls = list(row.vuls) + new_vuls
    await session.commit()
    # 替换附件时清理旧文件（更新失败时旧文件仍保留，不影响记录）
    if old_path and old_path != row.report_file_path:
        _remove_report_file(old_path)
    await session.refresh(row)
    await audit(session, request, "spring_action_change", user, {
        "op": "update", "target": f"spring-actions/{row_id}", "report_no": row.report_no,
        "attachment_replaced": bool(old_path and old_path != row.report_file_path),
    })
    return row


@router.get("/spring-actions/{row_id}/report")
async def download_spring_report(
    row_id: int,
    request: Request,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """下载春耕行动-原始报告附件（路径经 storage 边界校验，越界/缺失一律 404）。"""
    row = await get_or_404(session, SpringAction, row_id, "春耕行动记录不存在")
    if not row.report_file_path:
        raise HTTPException(404, "暂无原始报告附件")
    path = resolve_storage_path(row.report_file_path, not_found_detail="原始报告文件已被清理")
    await audit(session, request, "attachment_download", user, {
        "target": f"spring-actions/{row_id}", "file": row.report_file_name or path.name,
    })
    filename = quote(row.report_file_name or "report.docx")
    return FileResponse(
        path,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


def _remove_report_file(rel_path: str) -> None:
    """删除原始报告附件（尽力而为：路径越界或文件缺失时仅记录，不阻断业务）。

    路径同样走 storage 边界校验（审计 TALOS-2026-002）：DB 老数据可能残留非法路径，
    此处不得直接 unlink。"""
    try:
        path = resolve_storage_path(rel_path)
    except HTTPException:
        logger.warning("跳过删除非法附件路径 path=%s", rel_path)
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        # 尽力而为：文件被占用/无权限时仅记录，不阻断删除流程
        logger.warning("删除春耕行动报告附件失败 path=%s: %s", rel_path, exc)


@router.delete("/spring-actions/{row_id}")
async def delete_spring_action(
    row_id: int,
    request: Request,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(SpringAction, row_id)
    if row:
        if row.report_file_path:
            _remove_report_file(row.report_file_path)
        report_no = row.report_no
        await session.delete(row)
        await session.commit()
        await audit(session, request, "spring_action_change", user, {
            "op": "delete", "target": f"spring-actions/{row_id}", "report_no": report_no,
        })
    return {"msg": "删除成功"}
