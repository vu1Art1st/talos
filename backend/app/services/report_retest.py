"""报告复测编排：复测报告生成、标题查重与漏洞编辑快照（从 api/v1/reports.py 下沉，审计 E-3）。

路由层只保留鉴权、参数校验与响应组装；章节复制、重名规避、人天计算等编排逻辑放在此处，
便于与导入后的复测建单（`import_service`）共用同一口径。
"""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import mandays_between, now
from app.models import Report, ReportSection, User, Vul
from app.services.report_html import strip_embedded_retest


async def snapshot_vul_edits(session: AsyncSession, vul_ids: list[int]) -> dict:
    """对所选漏洞生成 {vul_id: update_time} 最后编辑时间快照（key 为字符串）。

    供报告相似性判定使用：生成/保存报告时写入快照，再次生成时对比所选漏洞
    当前的最后编辑时间，全部一致才视为「漏洞内容未变化」。
    """
    ids = [vid for vid in vul_ids if vid]
    if not ids:
        return {}
    rows = (
        await session.execute(select(Vul.id, Vul.update_time).where(Vul.id.in_(ids)))
    ).all()
    return {str(vid): t.isoformat() if t else "" for vid, t in rows}


async def report_title_exists(session: AsyncSession, title: str, plan_id: int | None) -> bool:
    """同计划范围内报告标题查重（无计划时按无归属计划口径查重）。"""
    cond = Report.title == title
    if plan_id is not None:
        cond = cond & (Report.testing_plan_id == plan_id)
    else:
        cond = cond & (Report.testing_plan_id.is_(None))
    return (
        await session.execute(select(Report.id).where(cond).limit(1))
    ).scalar_one_or_none() is not None


async def create_retest_report(
    session: AsyncSession, src: Report, user: User,
    vul_snapshot: dict | None = None,
) -> Report:
    """基于原报告自动生成复测报告。

    - 标题：当前发起复测日期（YYYYMMDD）为标题前八位，尾部将原「渗透测试报告」替换为「渗透测试复测报告」；
      同一天对同一来源重复发起复测导致标题重复时，自动追加「-1」「-2」后缀规避重名（不再复用旧报告）；
    - 测试周期：开始时间 = 发起复测当天，结束时间 = 生成当天（导出日期默认值，用户可手动修改）；
    - 章节复制原报告（保留漏洞关联），供复测编辑面板逐条处理；
    - 实际人天自动计算 = 结束日期 - 开始日期；
    - retest_vul_snapshot：记录本次发起复测后关联漏洞的状态快照，供下次发起复测时判断是否更新。
    """
    today = now().date()
    # 需求9：先清除原标题开头的旧日期（YYYYMMDD）再拼接当前日期，避免「yyyymmdyyyymmdd+系统名」重复
    base = re.sub(r"^\d{8}", "", src.title).replace("渗透测试报告", "渗透测试复测报告")
    title = f"{today.strftime('%Y%m%d')}{base}"
    suffix = 0
    candidate = title
    while await report_title_exists(session, candidate, src.testing_plan_id):
        suffix += 1
        candidate = f"{title}-{suffix}"
    report = Report(
        title=candidate,
        project_name=src.project_name,
        customer=src.customer,
        author=user.realname or user.username,
        target_ip=src.target_ip,
        test_start=today.isoformat(),
        test_end=today.isoformat(),
        testing_plan_id=src.testing_plan_id,
        creator_id=user.id,
        retest_vul_snapshot=vul_snapshot,
    )
    for s in src.sections:
        report.sections.append(ReportSection(
            order=s.order, title=s.title,
            # 章节正文不内嵌复测详情：复制时剥离历史内嵌段，复测详情由漏洞字段单独维护
            content_html=strip_embedded_retest(s.content_html),
            content_json=s.content_json, vul_id=s.vul_id,
        ))
    session.add(report)
    await session.flush()
    report.actual_mandays = mandays_between(report.test_start, report.test_end)
    report.vul_edit_snapshot = await snapshot_vul_edits(
        session, [s.vul_id for s in report.sections if s.vul_id]
    )
    return report
