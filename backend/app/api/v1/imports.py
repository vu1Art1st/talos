import logging
import uuid
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import DOCX_MIME
from app.core.config import settings
from app.core.query import get_or_404, paginate, apply_sort
from app.core.deps import require_perm
from app.db import get_session
from app.models import Asset, ExportJob, ImportBatch, ImportRecord, Report, TestingPlan, User
from app.schemas import (
    BatchConfirmIn,
    BatchConfirmItemOut,
    BatchConfirmOut,
    ImportBatchOut,
    ImportConfirmIn,
    ImportRecordOut,
    ImportRecordUpdateIn,
    Page,
)
from app.services import import_service
from app.services.audit_service import audit
from app.services.docx_parser import build_import_template
from app.services.exporter import cleanup_stale_previews, ensure_pdf_preview
from app.workers.dispatch import dispatch

router = APIRouter(prefix="/imports", tags=["Word导入"])

logger = logging.getLogger(__name__)


def _batch_chrono_key(batch: ImportBatch) -> tuple:
    """批量确认时序排序键：报告日期(旧→新) → 复测轮次 → 批次 id。

    同一工单下相同名称的漏洞会跨报告去重合并，必须按「旧报告 → 新报告」顺序处理，
    否则较新复测报告的「已修复」会被较旧报告（修复中/未修复）覆盖，
    导致最终漏洞状态与最新报告不一致（批量确认时序 bug）。
    """
    meta = batch.meta_json or {}
    date = (meta.get("report_date") or "").strip()
    seq = int(meta.get("retest_round_seq") or 0)
    return (date, seq, batch.id)


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


@router.post("/batch-confirm", response_model=BatchConfirmOut)
async def batch_confirm_batches(
    body: BatchConfirmIn,
    request: Request,
    user: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    """批量确认入库：勾选多个导入批次，统一指定工单/资产，逐批次复用单批确认逻辑。

    单批次失败只回滚该批次，不影响其余批次；无待入库记录（已确认/解析失败等）计入 skipped；
    返回各批次明细与本次生成/关联的报告 id 列表，前端据此调用批量导出。
    """
    batch_ids = list(dict.fromkeys(body.batch_ids))  # 去重保序
    if not batch_ids:
        raise HTTPException(400, "未选择任何导入批次")
    # 前置校验统一工单/资产，避免逐批次重复查询
    if body.testing_plan_id is not None:
        plan = await session.get(TestingPlan, body.testing_plan_id)
        if plan is None:
            raise HTTPException(400, "指定的渗透测试工单不存在")
    if body.asset_id is not None:
        asset = await session.get(Asset, body.asset_id)
        if asset is None:
            raise HTTPException(400, "指定的资产不存在")

    details: list[BatchConfirmItemOut] = []
    confirmed = skipped = failed = 0
    report_ids: list[int] = []
    # 预加载全部批次并按报告时序排序（旧→新）：同一工单下相同名称漏洞会跨报告去重合并，
    # 必须从旧到新处理，确保最新报告的「已修复」最终生效而非被较旧报告覆盖
    batches: list[tuple[int, ImportBatch | None]] = [
        (bid, await session.get(ImportBatch, bid)) for bid in batch_ids
    ]
    batches.sort(key=lambda item: _batch_chrono_key(item[1]) if item[1] is not None else ("", 0, 0))
    for bid, batch in batches:
        if batch is None:
            failed += 1
            details.append(BatchConfirmItemOut(
                batch_id=bid, filename="", status="failed", detail="导入批次不存在",
            ))
            continue
        # 预检查是否有待入库记录：无则跳过（已确认 / 部分确认后剩余为空 / 解析失败）
        has_parsed = (
            await session.execute(
                select(func.count(ImportRecord.id)).where(
                    ImportRecord.batch_id == bid, ImportRecord.status == "parsed",
                )
            )
        ).scalar_one()
        if not has_parsed:
            skipped += 1
            details.append(BatchConfirmItemOut(
                batch_id=bid, filename=batch.filename, status="skipped",
                detail="没有可入库的记录（可能已全部确认）",
            ))
            continue
        try:
            result = await import_service.confirm_batch_internal(
                session, batch, user,
                None, body.asset_id, None, body.testing_plan_id,
            )
            await audit(session, request, "import_confirm", user, {
                "target": f"imports/{bid}", "created": result.created,
            })
            confirmed += 1
            details.append(BatchConfirmItemOut(
                batch_id=bid, filename=batch.filename, status="confirmed", detail=result.msg,
            ))
            if result.report_id is not None:
                report_ids.append(result.report_id)
        except HTTPException as exc:
            await session.rollback()
            failed += 1
            details.append(BatchConfirmItemOut(
                batch_id=bid, filename=batch.filename, status="failed", detail=str(exc.detail),
            ))
        except Exception:
            await session.rollback()
            logger.exception("批量确认批次 %s 失败", bid)
            failed += 1
            details.append(BatchConfirmItemOut(
                batch_id=bid, filename=batch.filename, status="failed",
                detail="确认失败，请重试或进入预览逐批处理",
            ))
    return BatchConfirmOut(
        confirmed=confirmed, skipped=skipped, failed=failed,
        report_ids=report_ids, details=details,
    )


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
    request: Request,
    user: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    """确认入库：解析记录经知识库回填后建漏洞并去重合并，报告格式批次自动编排计划/资产/报告。"""
    batch = await get_or_404(session, ImportBatch, batch_id, "导入批次不存在")
    result = await import_service.confirm_batch_internal(
        session, batch, user,
        body.record_ids, body.asset_id, body.report_id, body.testing_plan_id,
    )
    await audit(session, request, "import_confirm", user, {
        "target": f"imports/{batch_id}", "created": result.created,
    })
    return {"msg": result.msg, "created": result.created}


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
