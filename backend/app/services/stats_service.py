"""安全态势聚合（dashboard 与开放 API /open/stats 共用，保证口径一致）。"""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_LEVEL, VUL_STATUS, VUL_TYPE
from app.core.timeutil import now as tznow, parse_date
from app.models import Asset, TestingPlan, Vul


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
    # 构造漏洞筛选条件，统一应用于各漏洞聚合查询
    vul_cond = []
    d_from = parse_date(date_from)
    if d_from:
        vul_cond.append(Vul.submit_time >= d_from)
    d_to = parse_date(date_to)
    if d_to:
        vul_cond.append(Vul.submit_time < d_to + timedelta(days=1))
    if source is not None:
        vul_cond.append(Vul.source == source)
    if level is not None:
        vul_cond.append(Vul.level == level)
    if department:
        vul_cond.append(
            Vul.testing_plan_id.in_(
                select(TestingPlan.id).where(TestingPlan.department == department)
            )
        )

    total_vulns = (await session.execute(select(func.count(Vul.id)).where(*vul_cond))).scalar_one()
    total_assets = (await session.execute(select(func.count(Asset.id)))).scalar_one()

    by_status_rows = (
        await session.execute(
            select(Vul.status, func.count(Vul.id)).where(*vul_cond).group_by(Vul.status)
        )
    ).all()
    by_status = [
        {"status": s, "name": VUL_STATUS.get(s, str(s)), "count": c}
        for s, c in by_status_rows
    ]

    by_level_rows = (
        await session.execute(
            select(Vul.level, func.count(Vul.id)).where(*vul_cond).group_by(Vul.level)
        )
    ).all()
    by_level = [
        {"level": lv, "name": VUL_LEVEL.get(lv, str(lv)), "count": c}
        for lv, c in by_level_rows
    ]

    by_type_rows = (
        await session.execute(
            select(Vul.vul_type, func.count(Vul.id))
            .where(*vul_cond)
            .group_by(Vul.vul_type)
            .order_by(func.count(Vul.id).desc())
        )
    ).all()
    # 应用层合并「其他」：未知类型码（含 NULL）与字典中的「其他(75)」统一归并为
    # 同一个「其他」分类，避免 Top10 图表出现两个「其他」条目
    merged: dict[str, int] = {}
    for t, c in by_type_rows:
        name = VUL_TYPE.get(t, "其他")
        merged[name] = merged.get(name, 0) + c
    by_type = [
        {
            "type": next((t for t, _ in by_type_rows if VUL_TYPE.get(t, "其他") == name), None),
            "name": name,
            "count": c,
        }
        for name, c in sorted(merged.items(), key=lambda x: x[1], reverse=True)
    ][:10]

    # 近12个月提交趋势（数据库无关：取一年内数据在应用层聚合），叠加筛选条件
    since = tznow() - timedelta(days=365)
    rows = (
        await session.execute(
            select(Vul.submit_time, Vul.status).where(Vul.submit_time >= since, *vul_cond)
        )
    ).all()
    trend: dict[str, dict[str, int]] = {}
    now = tznow()
    for i in range(11, -1, -1):
        month = (now.replace(day=1) - timedelta(days=30 * i)).strftime("%Y-%m")
        trend.setdefault(month, {"submitted": 0, "fixed": 0})
    for submit_time, status in rows:
        if submit_time is None:
            continue
        key = submit_time.strftime("%Y-%m")
        if key in trend:
            trend[key]["submitted"] += 1
            if status == 60:
                trend[key]["fixed"] += 1

    fixed = sum(c for s, c in by_status_rows if s == 60)
    closed = sum(c for s, c in by_status_rows if s in (20, 60))
    fix_rate = round(fixed / total_vulns * 100, 1) if total_vulns else 0.0

    # 部门维度（按测试计划所属部门聚合）：提测次数 / 发现漏洞 / 已修复 / 修复率
    plan_cond = [TestingPlan.department == department] if department else []
    plan_rows = (
        await session.execute(
            select(
                TestingPlan.id,
                TestingPlan.department,
                TestingPlan.stat_critical + TestingPlan.stat_high
                + TestingPlan.stat_medium + TestingPlan.stat_low,
            ).where(*plan_cond)
        )
    ).all()
    linked_rows = (
        await session.execute(
            select(Vul.testing_plan_id, Vul.status).where(Vul.testing_plan_id.is_not(None), *vul_cond)
        )
    ).all()
    linked: dict[int, dict[str, int]] = {}
    for plan_id, vul_status in linked_rows:
        agg = linked.setdefault(plan_id, {"total": 0, "fixed": 0})
        agg["total"] += 1
        if vul_status == 60:
            agg["fixed"] += 1
    dept_map: dict[str, dict[str, int]] = {}
    for plan_id, department, stat_sum in plan_rows:
        dept = dept_map.setdefault(
            department or "未填写", {"plans": 0, "vulns": 0, "linked": 0, "fixed": 0}
        )
        dept["plans"] += 1
        agg = linked.get(plan_id)
        if agg:
            # 有关联漏洞时以真实漏洞记录为准
            dept["vulns"] += agg["total"]
            dept["linked"] += agg["total"]
            dept["fixed"] += agg["fixed"]
        else:
            # 无关联漏洞时用计划手填统计补充发现数
            dept["vulns"] += stat_sum or 0
    by_department = sorted(
        (
            {
                "department": name,
                "plans": d["plans"],
                "vulns": d["vulns"],
                "fixed": d["fixed"],
                "fix_rate": round(d["fixed"] / d["linked"] * 100, 1) if d["linked"] else None,
            }
            for name, d in dept_map.items()
        ),
        key=lambda x: x["plans"],
        reverse=True,
    )

    return {
        "total_vulns": total_vulns,
        "total_assets": total_assets,
        "open_vulns": total_vulns - closed,
        "fix_rate": fix_rate,
        "by_status": by_status,
        "by_level": by_level,
        "by_type": by_type,
        "by_department": by_department,
        "trend": [{"month": k, **v} for k, v in sorted(trend.items())],
    }
