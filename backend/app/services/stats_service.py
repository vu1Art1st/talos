"""安全态势聚合（dashboard 与开放 API /open/stats 共用，保证口径一致）。"""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_LEVEL, VUL_STATUS, VUL_TYPE
from app.core.timeutil import now as tznow, parse_date
from app.models import Asset, TestingPlan, Vul

# 修复情况状态码（与 VulStatus 的数值口径一致；用于聚合层归并）
_STATUS_FIXED = 60
_STATUS_CLOSED = (20, 60)


def _vuln_scope_cond(
    date_from: str, date_to: str, source: int | None, level: int | None, department: str,
) -> list:
    """构造漏洞筛选条件（统一应用于本模块各漏洞聚合查询）。"""
    cond = []
    d_from = parse_date(date_from)
    if d_from:
        cond.append(Vul.submit_time >= d_from)
    d_to = parse_date(date_to)
    if d_to:
        # 区间含当日：用「次日零点」开区间
        cond.append(Vul.submit_time < d_to + timedelta(days=1))
    if source is not None:
        cond.append(Vul.source == source)
    if level is not None:
        cond.append(Vul.level == level)
    if department:
        cond.append(
            Vul.testing_plan_id.in_(
                select(TestingPlan.id).where(TestingPlan.department == department)
            )
        )
    return cond


async def _count_by(session: AsyncSession, cond: list, column) -> list:
    """按单列分组计数（状态 / 等级等 Vul 自身字段）。"""
    return (
        await session.execute(
            select(column, func.count(Vul.id)).where(*cond).group_by(column)
        )
    ).all()


async def _top_vul_types(session: AsyncSession, cond: list, limit: int = 10) -> list[dict]:
    """漏洞类型 Top N。

    应用层合并「其他」：未知类型码（含 NULL）与字典中的「其他(75)」统一归并为
    同一个「其他」分类，避免图表出现两个「其他」条目。
    """
    rows = (
        await session.execute(
            select(Vul.vul_type, func.count(Vul.id))
            .where(*cond)
            .group_by(Vul.vul_type)
            .order_by(func.count(Vul.id).desc())
        )
    ).all()
    merged: dict[str, int] = {}
    for t, c in rows:
        name = VUL_TYPE.get(t, "其他")
        merged[name] = merged.get(name, 0) + c
    return [
        {
            "type": next((t for t, _ in rows if VUL_TYPE.get(t, "其他") == name), None),
            "name": name,
            "count": c,
        }
        for name, c in sorted(merged.items(), key=lambda x: x[1], reverse=True)
    ][:limit]


def _build_trend(rows: list) -> list[dict]:
    """近 12 个月提交趋势（数据库无关：取一年内数据在应用层聚合）。"""
    now = tznow()
    trend: dict[str, dict[str, int]] = {}
    for i in range(11, -1, -1):
        month = (now.replace(day=1) - timedelta(days=30 * i)).strftime("%Y-%m")
        trend.setdefault(month, {"submitted": 0, "fixed": 0})
    for submit_time, status in rows:
        if submit_time is None:
            continue
        key = submit_time.strftime("%Y-%m")
        if key in trend:
            trend[key]["submitted"] += 1
            if status == _STATUS_FIXED:
                trend[key]["fixed"] += 1
    return [{"month": k, **v} for k, v in sorted(trend.items())]


def _agg_linked_vulns(rows: list) -> dict[int, dict[str, int]]:
    """按测试计划归并其关联漏洞：总数 / 已修复 / 已忽略 / 高危及以上。"""
    linked: dict[int, dict[str, int]] = {}
    for plan_id, vul_status, vul_level in rows:
        agg = linked.setdefault(plan_id, {"total": 0, "fixed": 0, "ignored": 0, "high": 0})
        agg["total"] += 1
        if vul_status == _STATUS_FIXED:
            agg["fixed"] += 1
        if vul_status == 20:
            agg["ignored"] += 1
        if vul_level in (10, 20):
            agg["high"] += 1
    return linked


def _dept_map(plan_rows: list, linked: dict[int, dict[str, int]]) -> dict[str, dict]:
    """部门维度聚合：提测次数 / 发现漏洞 / 已修复 / 已忽略 / 高危 / 人天。"""
    dept_map: dict[str, dict[str, int | float]] = {}
    for plan_id, department, stat_sum, high_sum, actual_mandays in plan_rows:
        dept = dept_map.setdefault(
            department or "未填写",
            {"plans": 0, "vulns": 0, "linked": 0, "fixed": 0, "ignored": 0, "high": 0, "mandays": 0.0},
        )
        dept["plans"] += 1
        dept["mandays"] += actual_mandays or 0
        agg = linked.get(plan_id)
        if agg:
            # 有关联漏洞时以真实漏洞记录为准
            dept["vulns"] += agg["total"]
            dept["linked"] += agg["total"]
            dept["fixed"] += agg["fixed"]
            dept["ignored"] += agg["ignored"]
            dept["high"] += agg["high"]
        else:
            # 无关联漏洞时用计划手填统计补充发现数（高危及以上取严重+高危两项）
            dept["vulns"] += stat_sum or 0
            dept["high"] += high_sum or 0
    return dept_map


async def _by_department_stats(session: AsyncSession, department: str, vul_cond: list) -> list[dict]:
    """部门维度统计（按提测次数倒序）。

    修复率分母仅取「有关联漏洞」的漏洞数：手填统计无状态概念，若计入分母会失真。
    """
    plan_cond = [TestingPlan.department == department] if department else []
    plan_rows = (
        await session.execute(
            select(
                TestingPlan.id,
                TestingPlan.department,
                TestingPlan.stat_critical + TestingPlan.stat_high
                + TestingPlan.stat_medium + TestingPlan.stat_low,
                TestingPlan.stat_critical + TestingPlan.stat_high,
                TestingPlan.actual_mandays,
            ).where(*plan_cond)
        )
    ).all()
    linked_rows = (
        await session.execute(
            select(Vul.testing_plan_id, Vul.status, Vul.level)
            .where(Vul.testing_plan_id.is_not(None), *vul_cond)
        )
    ).all()
    dept_map = _dept_map(plan_rows, _agg_linked_vulns(linked_rows))
    return sorted(
        (
            {
                "department": name,
                "plans": d["plans"],
                "vulns": d["vulns"],
                "high": d["high"],
                "fixed": d["fixed"],
                # 未闭环 = 发现数 − 已修复 − 已忽略（已忽略视同闭环；手填统计无状态概念，全算未闭环）
                "open": d["vulns"] - d["fixed"] - d["ignored"],
                "fix_rate": round(d["fixed"] / d["linked"] * 100, 1) if d["linked"] else None,
                "mandays": round(d["mandays"], 1),
            }
            for name, d in dept_map.items()
        ),
        key=lambda x: x["plans"],
        reverse=True,
    )


async def build_stats(
    session: AsyncSession,
    *,
    date_from: str = "",
    date_to: str = "",
    department: str = "",
    source: int | None = None,
    level: int | None = None,
) -> dict:
    """安全态势聚合：支持按事件多维筛选（时间范围/部门/来源/等级）后展示。"""
    vul_cond = _vuln_scope_cond(date_from, date_to, source, level, department)

    total_vulns = (await session.execute(select(func.count(Vul.id)).where(*vul_cond))).scalar_one()
    total_assets = (await session.execute(select(func.count(Asset.id)))).scalar_one()

    by_status_rows = await _count_by(session, vul_cond, Vul.status)
    by_level_rows = await _count_by(session, vul_cond, Vul.level)
    by_status = [
        {"status": s, "name": VUL_STATUS.get(s, str(s)), "count": c}
        for s, c in by_status_rows
    ]
    by_level = [
        {"level": lv, "name": VUL_LEVEL.get(lv, str(lv)), "count": c}
        for lv, c in by_level_rows
    ]
    by_type = await _top_vul_types(session, vul_cond)

    # 近 12 个月提交趋势：取一年内数据在应用层按月聚合
    trend_rows = (
        await session.execute(
            select(Vul.submit_time, Vul.status)
            .where(Vul.submit_time >= tznow() - timedelta(days=365), *vul_cond)
        )
    ).all()

    fixed = sum(c for s, c in by_status_rows if s == _STATUS_FIXED)
    closed = sum(c for s, c in by_status_rows if s in _STATUS_CLOSED)

    return {
        "total_vulns": total_vulns,
        "total_assets": total_assets,
        "open_vulns": total_vulns - closed,
        "fix_rate": round(fixed / total_vulns * 100, 1) if total_vulns else 0.0,
        "by_status": by_status,
        "by_level": by_level,
        "by_type": by_type,
        "by_department": await _by_department_stats(session, department, vul_cond),
        "trend": _build_trend(trend_rows),
    }
