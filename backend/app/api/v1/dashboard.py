from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_LEVEL, VUL_STATUS, VUL_TYPE
from app.core.deps import require_perm
from app.db import get_session
from app.models import Asset, TestingPlan, User, Vul

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def stats(
    _: User = Depends(require_perm("dashboard:view")),
    session: AsyncSession = Depends(get_session),
):
    total_vulns = (await session.execute(select(func.count(Vul.id)))).scalar_one()
    total_assets = (await session.execute(select(func.count(Asset.id)))).scalar_one()

    by_status_rows = (
        await session.execute(select(Vul.status, func.count(Vul.id)).group_by(Vul.status))
    ).all()
    by_status = [
        {"status": s, "name": VUL_STATUS.get(s, str(s)), "count": c}
        for s, c in by_status_rows
    ]

    by_level_rows = (
        await session.execute(select(Vul.level, func.count(Vul.id)).group_by(Vul.level))
    ).all()
    by_level = [
        {"level": lv, "name": VUL_LEVEL.get(lv, str(lv)), "count": c}
        for lv, c in by_level_rows
    ]

    by_type_rows = (
        await session.execute(
            select(Vul.vul_type, func.count(Vul.id))
            .group_by(Vul.vul_type)
            .order_by(func.count(Vul.id).desc())
            .limit(10)
        )
    ).all()
    by_type = [
        {"type": t, "name": VUL_TYPE.get(t, "其他"), "count": c}
        for t, c in by_type_rows
    ]

    # 近12个月提交趋势（数据库无关：取一年内数据在应用层聚合）
    since = datetime.utcnow() - timedelta(days=365)
    rows = (
        await session.execute(select(Vul.submit_time, Vul.status).where(Vul.submit_time >= since))
    ).all()
    trend: dict[str, dict[str, int]] = {}
    now = datetime.utcnow()
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
    plan_rows = (
        await session.execute(
            select(
                TestingPlan.id,
                TestingPlan.department,
                TestingPlan.stat_critical + TestingPlan.stat_high
                + TestingPlan.stat_medium + TestingPlan.stat_low,
            )
        )
    ).all()
    linked_rows = (
        await session.execute(
            select(Vul.testing_plan_id, Vul.status).where(Vul.testing_plan_id.is_not(None))
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
