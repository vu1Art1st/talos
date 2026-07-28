import uuid
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.deps import require_perm
from app.db import get_session
from app.models import Asset, ImportBatch, ImportRecord, Report, ReportSection, User, Vul, VulLog
from app.schemas import (
    ImportBatchOut,
    ImportConfirmIn,
    ImportRecordOut,
    ImportRecordUpdateIn,
    Page,
)
from app.services.docx_parser import build_import_template
from app.services import vuln_service
from app.workers.dispatch import dispatch

router = APIRouter(prefix="/imports", tags=["Word导入"])

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


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
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过 50MB")

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
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("import:manage")),
    session: AsyncSession = Depends(get_session),
):
    total = (await session.execute(select(func.count(ImportBatch.id)))).scalar_one()
    items = (
        await session.execute(
            select(ImportBatch).order_by(ImportBatch.id.desc())
            .offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
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
    record = await session.get(ImportRecord, record_id)
    if record is None:
        raise HTTPException(404, "记录不存在")
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
    record = await session.get(ImportRecord, record_id)
    if record is None:
        raise HTTPException(404, "记录不存在")
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
    batch = await session.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(404, "导入批次不存在")
    records = (
        await session.execute(
            select(ImportRecord).where(
                ImportRecord.batch_id == batch_id,
                ImportRecord.id.in_(body.record_ids),
                ImportRecord.status == "parsed",
            )
        )
    ).scalars().all()
    if not records:
        raise HTTPException(400, "没有可入库的记录（仅解析成功且未入库的记录可确认）")

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
    from app.api.v1.reports import _vuln_section_html

    created = 0
    new_vul_ids: list[int] = []
    for rec in records:
        vul = Vul(
            title=rec.title,
            vul_type=rec.vul_type,
            level=rec.level,
            affected_url=rec.affected_url,
            description_html=rec.description_html,
            reproduce_html=rec.reproduce_html,
            solution_html=rec.solution_html,
            source=60,  # Word导入
            submitter_id=user.id,
        )
        if asset is not None:
            vul.assets = [asset]
        session.add(vul)
        await session.flush()
        session.add(VulLog(
            vul_id=vul.id, user_id=user.id, username=user.username,
            action="Word导入创建", content=f"来源批次 #{batch_id}（{batch.filename}）",
        ))
        rec.status = "confirmed"
        rec.vul_id = vul.id
        new_vul_ids.append(vul.id)
        # 关联到指定报告：自动追加为漏洞章节
        if report is not None:
            session.add(ReportSection(
                report_id=report.id,
                order=len(report.sections) + created,
                title=vul.title,
                content_html=_vuln_section_html(vul),
                vul_id=vul.id,
            ))
        created += 1

    if report is not None:
        report.version += 1
        # 与报告编辑关联漏洞的行为一致：自动进入修复中
        await vuln_service.auto_transition(
            session, new_vul_ids, 50, user, f"关联报告《{report.title}》，自动进入修复中",
        )

    remaining = (
        await session.execute(
            select(func.count(ImportRecord.id)).where(
                ImportRecord.batch_id == batch_id,
                ImportRecord.status.in_(["parsed", "error"]),
            )
        )
    ).scalar_one()
    if remaining == 0:
        batch.status = "confirmed"
    await session.commit()
    return {"msg": f"成功创建 {created} 条漏洞记录", "created": created}


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
