"""导入数据治理（P1-5）：失败记录重试、重复候选视图、字段修正留痕与结果报告。

与 `import_service` 的分工：本模块只做「治理类」动作（重试、比对、留痕、导出结果），
不放库确认主流程（那条链路仍在 `import_service.confirm_batch_internal`）。
"""
from __future__ import annotations

import asyncio
import logging
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import IMPORT_OUTCOME_NAME, VUL_LEVEL
from app.core.config import settings
from app.models import ImportBatch, ImportRecord, ImportRecordChange, TestingPlan, User, Vul
from app.services.docx_parser import parse_any_docx

logger = logging.getLogger(__name__)

# 重复候选判定阈值与数量上限
_SIMILARITY_THRESHOLD = 0.5
_MAX_CANDIDATES = 5
_MAX_RECORDS_SCAN = 300

# 可修正字段（与 ImportRecordUpdateIn 一致，用于留痕）
_TRACKED_FIELDS = (
    "title", "vul_type", "level", "affected_url",
    "description_html", "reproduce_html", "solution_html",
)


async def record_changes(
    session: AsyncSession,
    rec: ImportRecord,
    changes: list[tuple[str, str, str]],
    user: User | None,
    *,
    source: str = "manual",
) -> int:
    """写入字段修正流水（字段 / 修正前后值 / 修正人）；返回写入条数。

    只记录确有变化且长度可控的字段值（富文本截断到 2000 字符，避免留痕表膨胀）。
    """
    count = 0
    for field, old_value, new_value in changes:
        if field not in _TRACKED_FIELDS or old_value == new_value:
            continue
        session.add(ImportRecordChange(
            record_id=rec.id, field=field,
            old_value=str(old_value or "")[:2000], new_value=str(new_value or "")[:2000],
            source=source, user_id=user.id if user else None,
            username=(user.username if user else ""),
        ))
        count += 1
    return count


def _first_url(raw: str) -> str:
    for line in (raw or "").splitlines():
        text = line.strip()
        if text:
            return text
    return ""


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").strip(), (b or "").strip()).ratio()


async def find_duplicate_candidates(session: AsyncSession, batch: ImportBatch) -> list[dict]:
    """重复漏洞候选视图：为每条待确认记录列出标题 / URL / 等级 / 关联工单与相似度。

    只读操作；结果供界面「合并到已有漏洞 / 保留为独立记录」选择。
    """
    records = (
        await session.execute(
            select(ImportRecord)
            .where(ImportRecord.batch_id == batch.id, ImportRecord.status == "parsed")
            .order_by(ImportRecord.seq)
            .limit(_MAX_RECORDS_SCAN)
        )
    ).scalars().all()

    groups: list[dict] = []
    for rec in records:
        title = (rec.title or "").strip()
        url = _first_url(rec.affected_url)
        if not title and not url:
            continue
        cond = []
        if title:
            cond.append(Vul.title == title)
            # 标题相近的长标题用前 12 字模糊检索，缩小候选集（避免全表扫描）
            if len(title) >= 12:
                cond.append(Vul.title.ilike(f"%{title[:12]}%"))
        if url:
            cond.append(Vul.affected_url.ilike(f"%{url}%"))
        rows = (
            await session.execute(
                select(Vul).where(or_(*cond)).order_by(Vul.id.desc()).limit(20)
            )
        ).scalars().all()

        candidates: list[dict] = []
        for vul in rows:
            sim = max(_similarity(title, vul.title), 1.0 if url and url in (vul.affected_url or "") else 0.0)
            if sim < _SIMILARITY_THRESHOLD:
                continue
            plan = await session.get(TestingPlan, vul.testing_plan_id) if vul.testing_plan_id else None
            candidates.append({
                "vul_id": vul.id, "title": vul.title, "level": vul.level, "status": vul.status,
                "affected_url": vul.affected_url, "testing_plan_id": vul.testing_plan_id,
                "ticket_id": plan.ticket_id if plan is not None else "",
                "similarity": round(sim, 3),
            })
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        if candidates or rec.merge_vul_id:
            groups.append({
                "record_id": rec.id, "title": rec.title, "level": rec.level,
                "affected_url": rec.affected_url, "merge_vul_id": rec.merge_vul_id,
                "candidates": candidates[:_MAX_CANDIDATES],
            })
    return groups


def _record_payload(raw: dict) -> dict:
    """解析器输出的 record dict → ImportRecord 列字段（剔除 errors 与未知键）。"""
    payload = {k: v for k, v in raw.items() if k not in ("errors", "level_text")}
    payload.pop("errors", None)
    return payload


async def retry_failed_records(session: AsyncSession, batch: ImportBatch) -> dict:
    """重试失败记录：重新解析原文档，只回填状态为 error 的记录。

    - 批次本身解析失败（status=failed）或无任何记录时，整批重建解析记录（同一批次行保留，
      审计链不断）；
    - 其余情况只重试 `status == "error"` 的记录，成功解析的记录保持不变（不重复入库）。
    """
    path = Path(settings.storage_path / batch.file_path)
    if not batch.file_path or not path.is_file():
        raise HTTPException(400, "原始导入文件已被清理，无法重试；请重新上传该文档")
    image_dir = settings.storage_sub("uploads", "images")
    doc_kind, meta, records = await asyncio.to_thread(
        parse_any_docx, batch.file_path, str(image_dir), "/storage/uploads/images", batch.filename,
    )
    by_seq = {idx: _record_payload(rec) for idx, rec in enumerate(records, start=1)}
    errors_by_seq = {idx: rec.get("errors", []) for idx, rec in enumerate(records, start=1)}

    existing = (
        await session.execute(
            select(ImportRecord).where(ImportRecord.batch_id == batch.id).order_by(ImportRecord.seq)
        )
    ).scalars().all()

    if batch.status == "failed" or not existing:
        # 整批重建：删除旧记录后按新解析结果落库
        for row in existing:
            await session.delete(row)
        await session.flush()
        success = failed = 0
        for seq, raw in by_seq.items():
            errors = errors_by_seq.get(seq) or []
            status = "error" if errors and not raw.get("title") else "parsed"
            success += 0 if status == "error" else 1
            failed += 1 if status == "error" else 0
            session.add(ImportRecord(
                batch_id=batch.id, seq=seq, status=status,
                parse_error="；".join(errors), **raw,
            ))
        batch.doc_kind = doc_kind
        batch.meta_json = meta
        batch.total = len(by_seq)
        batch.success = success
        batch.failed = failed
        batch.error = "" if success else batch.error
        batch.status = "parsed" if success else "failed"
        batch.dead_letter_reason = ""
        return {
            "batch_id": batch.id, "scope": "batch",
            "retried": len(by_seq), "resolved": success, "still_failed": failed,
            "msg": f"已整批重新解析：成功 {success} 条，失败 {failed} 条",
        }

    retried = resolved = 0
    for row in existing:
        if row.status != "error":
            continue
        retried += 1
        raw = by_seq.get(row.seq)
        errors = errors_by_seq.get(row.seq) or []
        if raw is None:
            row.parse_error = row.parse_error or "重试未能在文档中定位该条记录"
            continue
        if errors and not raw.get("title"):
            row.parse_error = "；".join(errors)
            continue
        for key, value in raw.items():
            if hasattr(row, key):
                setattr(row, key, value)
        row.parse_error = ""
        row.status = "parsed"
        resolved += 1
    still_failed = retried - resolved
    if resolved:
        batch.failed = max(int(batch.failed or 0) - resolved, 0)
        batch.success = int(batch.success or 0) + resolved
    return {
        "batch_id": batch.id, "scope": "failed",
        "retried": retried, "resolved": resolved, "still_failed": still_failed,
        "msg": f"已重试失败记录 {retried} 条：成功 {resolved} 条，仍失败 {still_failed} 条",
    }


def build_result_report(batch: ImportBatch, records: list[ImportRecord]) -> Workbook:
    """批量确认结果报告（xlsx）：新增 / 更新 / 合并 / 跳过 / 失败及原因。

    结果与数据库最终状态一致（直接读 `import_records.outcome/status`），
    可由脚本复核；不依赖调用方的内存计数。
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "导入结果"
    headers = ["序号", "漏洞标题", "等级", "状态", "入库结果", "结果说明", "漏洞ID", "影响URL"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    counter: dict[str, int] = {}
    for rec in records:
        outcome = rec.outcome or (
            "failed" if rec.status == "error" else ("skipped" if rec.status == "discarded" else "")
        )
        counter[outcome or "pending"] = counter.get(outcome or "pending", 0) + 1
        reason = rec.outcome_reason or rec.parse_error or (
            "尚未入库" if rec.status in ("parsed", "error") else ""
        )
        ws.append([
            rec.seq, rec.title, VUL_LEVEL.get(rec.level, str(rec.level)),
            rec.status,
            IMPORT_OUTCOME_NAME.get(outcome, outcome or "未入库"),
            reason, rec.vul_id or "", rec.affected_url or "",
        ])

    summary = wb.create_sheet("汇总")
    summary.append(["批次", batch.filename])
    summary.append(["批次状态", batch.status])
    summary.append(["记录总数", len(records)])
    for key, name in IMPORT_OUTCOME_NAME.items():
        summary.append([name, counter.get(key, 0)])
    summary.append(["未入库", counter.get("pending", 0)])
    summary.append(["丢弃", counter.get("discarded", 0)])
    for cell in summary["A"]:
        cell.font = Font(bold=True)
    ws.column_dimensions["B"].width = 46
    ws.column_dimensions["F"].width = 40
    ws.column_dimensions["H"].width = 40
    return wb


def workbook_bytes(wb: Workbook) -> BytesIO:
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
