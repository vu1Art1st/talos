"""报告模板中心（P1-4）：上传、校验、发布、回滚、试生成与下载。"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DOCX_MIME, REPORT_TEMPLATE_TYPES
from app.core.archive import assert_archive_quota
from app.core.deps import require_perm
from app.core.query import get_or_404, paginate
from app.core.storage import require_attachment_path, resolve_storage_path
from app.db import get_session
from app.models import ReportTemplate, User
from app.schemas import (
    Page,
    ReportTemplateOut,
    TemplatePreviewOut,
    TemplateValidateOut,
)
from app.services import template_service
from app.services.audit_service import audit
from app.services.upload_store import save_upload

router = APIRouter(prefix="/report-templates", tags=["报告模板"])

MAX_TEMPLATE_BYTES = 50 * 1024 * 1024

# 上传失败/非法类型时统一文案
_BAD_TYPE_MSG = f"模板类型仅支持 {list(REPORT_TEMPLATE_TYPES)}"


def _check_type(report_type: str) -> str:
    if report_type not in REPORT_TEMPLATE_TYPES:
        raise HTTPException(400, _BAD_TYPE_MSG)
    return report_type


def _missing_error(missing: list[str]) -> HTTPException:
    """占位符缺失异常（附字段清单，便于界面直接展示）。"""
    return HTTPException(400, "模板占位符缺失，已阻止发布：" + "；".join(missing))


@router.get("", response_model=Page[ReportTemplateOut])
async def list_templates(
    report_type: str = "",
    active_only: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if report_type:
        cond.append(ReportTemplate.report_type == report_type)
    if active_only:
        cond.append(ReportTemplate.is_active.is_(True))
    total, items = await paginate(
        session,
        select(ReportTemplate).where(*cond)
        .order_by(ReportTemplate.name, ReportTemplate.version.desc()),
        page, size,
    )
    return Page(total=total, items=[ReportTemplateOut.model_validate(i) for i in items])


@router.post("", response_model=ReportTemplateOut)
async def upload_template(
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(..., min_length=1, max_length=128),
    report_type: str = Form("all"),
    remark: str = Form(""),
    publish: bool = Form(False),
    operator: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """上传模板：文件安全校验 → 锚点占位符校验 → 版本 +1 落库（可选立即发布）。

    占位符缺失时阻止发布（400 并返回缺失字段清单）。
    """
    _check_type(report_type)
    original_name, rel_path, size = await save_upload(
        file, "templates",
        max_bytes=MAX_TEMPLATE_BYTES,
        require_ext=".docx",
        magic=b"PK\x03\x04",
        magic_error="文件内容不是有效的 .docx（Word）文档",
        size_error="模板文件大小不能超过 50MB",
    )
    rel_path = require_attachment_path(rel_path, subdir="templates")
    abs_path = resolve_storage_path(rel_path, not_found_detail="模板文件写入失败")
    # 解压配额守卫（zip 炸弹）：解析前先判，避免 Python-docx 解压耗尽内存
    assert_archive_quota(abs_path)
    ok, missing, anchors = template_service.validate_docx(abs_path)
    if publish and not ok:
        raise _missing_error(missing)

    max_version = (
        await session.execute(
            select(func.max(ReportTemplate.version)).where(ReportTemplate.name == name.strip())
        )
    ).scalar_one()
    row = ReportTemplate(
        name=name.strip(), report_type=report_type, version=int(max_version or 0) + 1,
        is_active=False, file_path=rel_path, original_filename=original_name,
        size_bytes=size, anchors=anchors, remark=remark, creator_id=operator.id,
    )
    session.add(row)
    await session.flush()
    if publish:
        row.is_active = True
        await template_service.deactivate_siblings(session, row)
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "template_publish" if publish else "template_activate", operator, {
        "op": "upload", "name": row.name, "version": row.version,
        "report_type": report_type, "published": publish, "missing": missing,
    })
    return row


@router.post("/{template_id}/validate", response_model=TemplateValidateOut)
async def validate_template(
    template_id: int,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """重新校验模板占位符（发布前二次确认），返回缺失清单与锚点信息。"""
    row = await get_or_404(session, ReportTemplate, template_id, "模板不存在")
    path = resolve_storage_path(row.file_path, not_found_detail="模板文件已被清理")
    ok, missing, anchors = template_service.validate_docx(path)
    return TemplateValidateOut(ok=ok, missing=missing, anchors=anchors)


@router.post("/{template_id}/publish", response_model=ReportTemplateOut)
async def publish_template(
    template_id: int,
    request: Request,
    operator: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """发布模板版本：校验通过后启用，并停用同名的其他版本。"""
    row = await get_or_404(session, ReportTemplate, template_id, "模板不存在")
    path = resolve_storage_path(row.file_path, not_found_detail="模板文件已被清理")
    ok, missing, anchors = template_service.validate_docx(path)
    if not ok:
        raise _missing_error(missing)
    row.anchors = anchors
    row.is_active = True
    await template_service.deactivate_siblings(session, row)
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "template_publish", operator, {
        "name": row.name, "version": row.version,
    })
    return row


@router.post("/{template_id}/activate", response_model=ReportTemplateOut)
async def activate_template(
    template_id: int,
    request: Request,
    operator: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """启用指定版本（历史版本回滚）。"""
    row = await get_or_404(session, ReportTemplate, template_id, "模板不存在")
    path = resolve_storage_path(row.file_path, not_found_detail="模板文件已被清理")
    ok, missing, _anchors = template_service.validate_docx(path)
    if not ok:
        raise _missing_error(missing)
    row.is_active = True
    await template_service.deactivate_siblings(session, row)
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "template_activate", operator, {
        "name": row.name, "version": row.version,
    })
    return row


@router.post("/{template_id}/preview", response_model=TemplatePreviewOut)
async def preview_template(
    template_id: int,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """示例数据试生成：用示例 meta / 漏洞 / 章节生成 docx，返回下载地址。

    `url` 为**相对 API 基址**的路径（前端 `client` 的 baseURL 即 `/api/v1`），
    与站内其它下载接口的调用方式一致，避免出现 `/api/v1/api/v1/...` 的双前缀。
    """
    row = await get_or_404(session, ReportTemplate, template_id, "模板不存在")
    path = resolve_storage_path(row.file_path, not_found_detail="模板文件已被清理")
    rel = template_service.preview_docx(path)
    name = rel.rsplit("/", 1)[-1]
    return TemplatePreviewOut(
        url=f"/report-templates/previews/{name}",
        msg="示例报告已生成，可直接下载查看模板效果",
    )


@router.get("/previews/{name}")
async def download_preview(
    name: str,
    _: User = Depends(require_perm("report:manage")),
):
    """下载试生成文件（路径经 storage 白名单解析，越界/不存在统一 404）。"""
    path = resolve_storage_path(f"uploads/previews/{name}", not_found_detail="试生成文件已被清理")
    return FileResponse(str(path), media_type=DOCX_MIME, filename="模板试生成示例.docx")


@router.get("/{template_id}/download")
async def download_template(
    template_id: int,
    _: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, ReportTemplate, template_id, "模板不存在")
    path = resolve_storage_path(row.file_path, not_found_detail="模板文件已被清理")
    return FileResponse(
        str(path), media_type=DOCX_MIME,
        filename=row.original_filename or f"{row.name}-v{row.version}.docx",
    )


@router.delete("/{template_id}")
async def delete_template(
    template_id: int,
    request: Request,
    operator: User = Depends(require_perm("report:manage")),
    session: AsyncSession = Depends(get_session),
):
    """删除模板版本：**启用中的版本不可删除**（先启用其他版本再删）。"""
    row = await get_or_404(session, ReportTemplate, template_id, "模板不存在")
    if row.is_active:
        raise HTTPException(400, "启用中的模板版本不可删除，请先启用其他版本")
    name, version, rel_path = row.name, row.version, row.file_path
    await session.delete(row)
    await session.commit()
    try:
        resolve_storage_path(rel_path).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001  文件已清理不影响删除结果
        pass
    await audit(session, request, "template_delete", operator, {"name": name, "version": version})
    return {"msg": "删除成功"}
