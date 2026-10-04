"""报告手动导出前的周期解析与完整性预检。"""
from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import now
from app.models import Report, Vul
from app.services import report_meta
from app.services.report_targets import build_target_info

MISSING_AUTHOR = "author"
MISSING_TEST_PERIOD = "test_period"
MISSING_TARGET_IP = "target_ip"
MISSING_TEST_ACCOUNT = "test_account"


async def resolve_test_period(session: AsyncSession, report: Report) -> tuple[str, str]:
    """返回导出将实际使用的测试周期，保持现有自动预填口径。"""
    test_start = (report.test_start or "").strip()
    test_end = (report.test_end or "").strip()
    if test_start and test_end:
        return test_start, test_end

    vul_ids = [s.vul_id for s in report.sections if s.vul_id]
    if not test_start and vul_ids:
        earliest = (
            await session.execute(
                select(func.min(Vul.submit_time)).where(Vul.id.in_(vul_ids))
            )
        ).scalar_one_or_none()
        if earliest is not None:
            test_start = earliest.date().isoformat()
    if not test_end:
        test_end = now().date().isoformat()
    return test_start, test_end


async def missing_export_fields(session: AsyncSession, report: Report) -> list[str]:
    """返回手动导出确认弹窗需要展示的字段代码（固定顺序）。"""
    missing: list[str] = []
    if not (report.author or "").strip():
        missing.append(MISSING_AUTHOR)

    test_start, test_end = await resolve_test_period(session, report)
    if not test_start or not test_end:
        missing.append(MISSING_TEST_PERIOD)

    plan = await report_meta.resolve_plan(session, report)
    sections = report_meta.build_sections(report)
    vulns, assets = await report_meta.collect_vulns_and_assets(session, sections)
    targets = await asyncio.to_thread(
        build_target_info,
        meta={"target_ip": report.target_ip},
        assets=assets,
        plan_urls=report_meta.collect_plan_urls(plan),
        vulns=vulns,
    )
    if not any(ip.strip() for ip in targets.ips):
        missing.append(MISSING_TARGET_IP)

    if not (report.test_account or "").strip():
        missing.append(MISSING_TEST_ACCOUNT)
    return missing
