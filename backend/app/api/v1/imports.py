import logging
import uuid
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import DOCX_MIME
from app.core.config import settings
from app.core.query import get_or_404, paginate, apply_sort
from app.core.deps import require_perm
from app.db import get_session
from app.models import Asset, ImportBatch, ImportRecord, Report, TestingPlan, User
from app.schemas import (
    ImportBatchOut,
    ImportConfirmIn,
    ImportRecordOut,
    ImportRecordUpdateIn,
    Page,
)
from app.services import import_service
from app.services.docx_parser import build_import_template
from app.services.exporter import cleanup_stale_previews, ensure_pdf_preview
from app.workers.dispatch import dispatch

router = APIRouter(prefix="/imports", tags=["Word导入"])

logger = logging.getLogger(__name__)

# .docx 本质是 ZIP 包，ZIP 文件头魔术字节为 PK\x03\x04
DOCX_MAGIC = b"PK\x03\x04"
MAX_UPLOAD_BYTES = 50 * 1024 * 1024


@router.get("/template")
async def download_template(_: User = Depends(require_perm("import:manage"))):
    doc = build_import_template()
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    filename = quote("漏洞导入模板.docx")
    return StreamingResponse(
        buf,
        media_type=DOCX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("", response_model=ImportBatchOut)
async def upload_docx(
    request: Request,
    file: UploadFile,
    user: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(400, "仅支持 .docx 格式的 Word 文档")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "文件大小不能超过 50MB")
    # 校验魔术字节，防止伪造扩展名的非 ZIP/docx 文件进入解析流程
    if not data.startswith(DOCX_MAGIC):
        raise HTTPException(400, "文件内容不是有效的 .docx（Word）文档")

    upload_dir = settings.storage_sub("uploads", "imports")
    path = upload_dir / f"{uuid.uuid4().hex}.docx"
    path.write_bytes(data)

    batch = ImportBatch(filename=file.filename, file_path=str(path), creator_id=user.id)
    session.add(batch)
    await session.commit()
    await session.refresh(batch)

    await dispatch(request.app, "parse_import_task", batch.id)
    return batch


@router.get("", response_model=Page[ImportBatchOut])
async def list_batches(
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(ImportBatch)
    stmt = apply_sort(
        stmt, ImportBatch, sort, order,
        {"id", "filename", "status", "total", "success", "failed", "create_time"},
        ImportBatch.id.desc(),
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=items)


@router.get("/{batch_id}")
async def batch_detail(
    batch_id: int,
    _: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    batch = (
        await session.execute(
            select(ImportBatch).options(selectinload(ImportBatch.records))
            .where(ImportBatch.id == batch_id)
        )
    ).scalar_one_or_none()
    if batch is None:
        raise HTTPException(404, "导入批次不存在")
    return {
        "batch": ImportBatchOut.model_validate(batch),
        "records": [ImportRecordOut.model_validate(r) for r in batch.records],
    }


@router.put("/records/{record_id}", response_model=ImportRecordOut)
async def update_record(
    record_id: int,
    body: ImportRecordUpdateIn,
    _: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    record = await get_or_404(session, ImportRecord, record_id, "记录不存在")
    if record.status == "confirmed":
        raise HTTPException(400, "已确认入库的记录不能修改")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(record, k, v)
    if record.title and record.status == "error":
        record.status = "parsed"
        record.parse_error = ""
    await session.commit()
    await session.refresh(record)
    return record


@router.post("/records/{record_id}/discard", response_model=ImportRecordOut)
async def discard_record(
    record_id: int,
    _: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    record = await get_or_404(session, ImportRecord, record_id, "记录不存在")
    if record.status == "confirmed":
        raise HTTPException(400, "已确认入库的记录不能丢弃")
    record.status = "discarded"
    await session.commit()
    return record


@router.post("/{batch_id}/confirm")
async def confirm_batch(
    batch_id: int,
    body: ImportConfirmIn,
    user: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    """确认入库：解析记录经知识库回填后建漏洞并去重合并，报告格式批次自动编排计划/资产/报告。"""
    batch = await get_or_404(session, ImportBatch, batch_id, "导入批次不存在")
    records = await import_service.load_parsed_records(session, batch_id, body.record_ids)

    asset = None
    if body.asset_id is not None:
        asset = await session.get(Asset, body.asset_id)
        if asset is None:
            raise HTTPException(400, "指定的资产不存在")

    report = None
    if body.report_id is not None:
        report = await session.get(Report, body.report_id)
        if report is None:
            raise HTTPException(400, "指定的报告不存在")

    # 显式关联的测试计划（任何文档格式均可指定）
    plan = None
    if body.testing_plan_id is not None:
        plan = await session.get(TestingPlan, body.testing_plan_id)
        if plan is None:
            raise HTTPException(400, "指定的渗透测试工单不存在")

    batch_meta = batch.meta_json or {}
    is_retest = batch.doc_kind == "report" and bool(batch_meta.get("is_retest"))
    all_fixed = all(rec.fixed for rec in records)  # records 恒非空（上方已校验）

    # 报告格式批次：确认入库时自动创建/关联测试计划、资产与报告
    report_auto_created = False
    if batch.doc_kind == "report":
        plan, round_row = await import_service.resolve_report_plan(
            session, batch, user, plan, is_retest, all_fixed,
        )
        if plan is not None:
            asset = await import_service.resolve_report_asset(session, batch, plan, asset)
            report, report_auto_created = await import_service.ensure_report_and_bind_round(
                session, batch, plan, user, report, round_row,
            )

    kb_map = await import_service.load_knowledge_map(session, records)
    created = 0
    new_vul_ids: list[int] = []
    for rec in records:
        vul, is_new = await import_service.confirm_one_record(
            session, batch, rec, plan, asset, report, user, kb_map, is_retest, created,
        )
        if is_new:
            new_vul_ids.append(vul.id)
        created += 1

    await import_service.finalize_confirm(
        session, batch, plan, report, report_auto_created, new_vul_ids, user,
    )
    await session.commit()
    msg = f"成功处理 {created} 条漏洞记录"
    if plan is not None:
        msg += f"，已关联测试计划「{plan.system_name}」"
    if report_auto_created and report is not None:
        msg += f"，已生成报告「{report.title}」"
    return {"msg": msg, "created": created}


@router.get("/{batch_id}/preview")
async def preview_batch(
    batch_id: int,
    _: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    """在线预览导入原文件：docx 临时转为 PDF 展示。"""
    batch = await get_or_404(session, ImportBatch, batch_id, "导入批次不存在")
    cleanup_stale_previews()  # 顺带清理过期预览
    try:
        pdf_path = await ensure_pdf_preview(batch.file_path)
    except FileNotFoundError:
        raise HTTPException(404, "导入文件已被清理")
    except Exception:
        logger.exception("预览转换失败 batch_id=%s", batch_id)
        raise HTTPException(502, "预览转换失败，请稍后重试或联系管理员")
    filename = quote(f"{batch.filename.rsplit('.', 1)[0]}.pdf")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"},
    )


@router.delete("/{batch_id}")
async def delete_batch(
    batch_id: int,
    _: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    batch = await session.get(ImportBatch, batch_id)
    if batch:
        await session.delete(batch)
        await session.commit()
    return {"msg": "删除成功"}
