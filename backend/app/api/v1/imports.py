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
from app.core.timeutil import utcnow
from app.core.deps import require_perm
from app.db import get_session
from app.models import Asset, ImportBatch, ImportRecord, KnowledgeEntry, Report, ReportSection, TestingPlan, User, Vul, VulLog
from app.schemas import (
    ImportBatchOut,
    ImportConfirmIn,
    ImportRecordOut,
    ImportRecordUpdateIn,
    Page,
)
from app.services.docx_parser import build_import_template
from app.services import plan_service, vuln_service
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
    batch = await get_or_404(session, ImportBatch, batch_id, "导入批次不存在")
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

    # 显式关联的测试计划（任何文档格式均可指定）
    plan = None
    if body.testing_plan_id is not None:
        plan = await session.get(TestingPlan, body.testing_plan_id)
        if plan is None:
            raise HTTPException(400, "指定的测试计划不存在")

    from app.api.v1.reports import _vuln_section_html

    batch_meta = batch.meta_json or {}
    is_retest = batch.doc_kind == "report" and bool(batch_meta.get("is_retest"))
    all_fixed = all(rec.fixed for rec in records)  # records 恒非空（上方已校验）

    # 报告格式批次：确认入库时自动创建/关联测试计划、资产与报告
    report_auto_created = False
    if batch.doc_kind == "report":
        system_name = (batch_meta.get("system_name") or "").strip()
        if plan is None:
            # 未显式指定计划：按系统名自动匹配，不存在则创建
            if system_name:
                plan = (
                    await session.execute(
                        select(TestingPlan).where(TestingPlan.system_name == system_name)
                    )
                ).scalars().first()
                if plan is None:
                    plan = TestingPlan(system_name=system_name, test_type="渗透测试", creator_id=user.id)
                    session.add(plan)
        if plan is not None:
            await session.flush()  # 确保 plan.id 可用于复测轮次与报告关联
            # 复测轮次为惰性关系，新建计划需显式加载后才能在同步逻辑中访问
            await session.refresh(plan, attribute_names=["retest_rounds"])
            report_date = batch_meta.get("report_date") or ""
            if is_retest:
                # 按记录实际修复情况判定：全部修复才算复测完成，否则仍处于复测中
                if all_fixed:
                    plan.status = 60  # 复测完成
                    plan.retest_done_time = report_date or plan.retest_done_time
                    plan_service.finish_retest_round(plan)
                else:
                    plan.status = 50  # 复测中：仍有未修复漏洞待闭环
                    plan_service.start_retest_round(session, plan, "报告导入复测", user.id, force=True)
            else:
                plan.status = 30  # 初测完成，等待复测
                plan.first_test_done_time = report_date or plan.first_test_done_time

            # 自动新增/更新资产：按系统名匹配，无则创建，被测 URL/IP 补齐
            if asset is None:
                if system_name:
                    asset = (
                        await session.execute(select(Asset).where(Asset.name == system_name))
                    ).scalars().first()
                    target_url = (batch_meta.get("target_url") or "").strip()
                    target_ip = (batch_meta.get("target_ip") or "").strip()
                    if asset is None:
                        remark = "导入报告自动创建"
                        if target_ip:
                            remark += f"；被测IP：{target_ip}"
                        asset = Asset(name=system_name, remark=remark)
                        session.add(asset)
                    if target_url:
                        urls = list(asset.internal_urls or [])
                        if target_url not in urls:
                            urls.append(target_url)
                            asset.internal_urls = urls
                    await session.flush()
                elif plan.asset_ids:
                    # 无系统名但计划已关联资产时，默认入库到首个关联资产
                    asset = await session.get(Asset, plan.asset_ids[0])
            # 本次入库的资产自动关联到计划，保持「资产关联前置至计划」的一致性
            if plan is not None and asset is not None:
                plan_asset_ids = list(plan.asset_ids or [])
                if asset.id not in plan_asset_ids:
                    plan_asset_ids.append(asset.id)
                    plan.asset_ids = plan_asset_ids

            # 自动创建报告：使导入报告显示在报告中心，并支持复测信息编辑
            if report is None:
                report = Report(
                    title=batch.filename.rsplit(".", 1)[0],
                    project_name=system_name or plan.system_name,
                    target_ip=(batch_meta.get("target_ip") or ""),
                    testing_plan_id=plan.id,
                    creator_id=user.id,
                    status="completed" if all_fixed else "draft",
                )
                session.add(report)
                await session.flush()
                await session.refresh(report, attribute_names=["sections"])
                report_auto_created = True

    created = 0
    new_vul_ids: list[int] = []
    # 知识库回填：解析内容为空的描述/修复建议，自动套用对应漏洞类型的模板
    # 同类型多条时取危害等级最高、最早创建的一条（与 /knowledge/by-type 语义一致）
    kb_types = {rec.vul_type for rec in records}
    kb_map: dict[int, KnowledgeEntry] = {}
    for e in (
        await session.execute(
            select(KnowledgeEntry)
            .where(KnowledgeEntry.vul_type.in_(kb_types))
            .order_by(KnowledgeEntry.severity_level.desc(), KnowledgeEntry.id.desc())
        )
    ).scalars().all():
        kb_map[e.vul_type] = e  # 降序遍历，最后覆盖的即为等级最高、id 最小的一条
    for rec in records:
        kb = kb_map.get(rec.vul_type)
        description_html = rec.description_html
        solution_html = rec.solution_html
        if kb is not None:
            if not (description_html or "").strip() and kb.description_html:
                description_html = kb.description_html
                if kb.harm_html:
                    description_html += f"<p><strong>危害说明：</strong></p>{kb.harm_html}"
            if not (solution_html or "").strip() and kb.solution_html:
                solution_html = kb.solution_html
        vul = Vul(
            title=rec.title,
            vul_type=rec.vul_type,
            level=rec.level,
            affected_url=rec.affected_url,
            description_html=description_html,
            reproduce_html=rec.reproduce_html,
            solution_html=solution_html,
            source=60,  # Word导入
            submitter_id=user.id,
        )
        # 显式指定或报告格式自动匹配的测试计划：任何文档格式均关联漏洞
        if plan is not None:
            vul.testing_plan_id = plan.id
        if batch.doc_kind == "report":
            vul.is_retest = bool(batch_meta.get("is_retest"))
            vul.retest_html = rec.retest_html
            if rec.fixed:
                vul.status = 60  # 报告中标记已修复
                vul.fix_time = utcnow()
            elif is_retest:
                vul.status = 55  # 复测报告中仍未修复：进入复测中，可在报告编辑页填写复测结论
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

    if report is not None and not report_auto_created:
        report.revision += 1  # 追加章节属编辑操作，仅自增编辑锁；导出版本号只在导出成功时 +1
        # 与报告编辑关联漏洞的行为一致：自动进入修复中
        await vuln_service.auto_transition(
            session, new_vul_ids, 50, user, f"关联报告《{report.title}》，自动进入修复中",
        )

    if plan is not None:
        await plan_service.refresh_stats(session, plan.id)

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
    msg = f"成功创建 {created} 条漏洞记录"
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
