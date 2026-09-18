"""测试计划查询支撑：固定参数筛选、聚合筛选（filters JSON）与多维度统计。

列表 / 统计 / 导出三个入口共用的条件拼装都集中在此，路由层只做参数编排。
聚合筛选的通用表达式构造在 core/filters.py，本模块补充 TestingPlan 特有的
派生字段（工单ID、测试人员多对多、关联计数）。
关键词搜索（plan_search_condition / nonpen_search_condition）与聚合筛选的
工单ID表达式（_ticket_id_filter_expr）口径一致：手动指定值优先，否则由
receive_time(YYYY-MM-DD) + ticket_seq 派生 YYYYMMDD-N。
"""
import re
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import String, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import TESTING_PLAN_STATUS, PlanStatus
from app.core.filters import (
    ALLOWED_FILTER_OPS,
    build_filter_expr,
    combine_rules,
    parse_filter_rules,
    split_range,
    to_float,
)
from app.core.timeutil import now as tznow
from app.models import (
    NonpenPlan,
    Report,
    TestingPlan,
    TestingPlanRetestRound,
    User,
    Vul,
    testing_plan_testers,
)


def nonpen_search_condition(search: str):
    """漏扫基线工单搜索：计划名称 / 测试系统 / 所属部门 / 工单ID（手动指定值，
    或 YYYYMMDD-N 自动编号的日期+序号组合）。站内列表与开放 API 共用。"""
    pat = f"%{search}%"
    conds = [
        NonpenPlan.plan_name.ilike(pat),
        NonpenPlan.system_name.ilike(pat),
        NonpenPlan.department.ilike(pat),
        NonpenPlan.ticket_id_manual.ilike(pat),
        NonpenPlan.receive_time.ilike(pat),
        func.replace(NonpenPlan.receive_time, "-", "").ilike(pat),
        func.cast(NonpenPlan.ticket_seq, String).ilike(pat),
    ]
    # 完整工单ID匹配：YYYYMMDD-N（如 20260810-3）→ 手动指定值本身，或自动编号的日期+当日序号组合
    m = re.fullmatch(r"(\d{8})-(\d+)", search)
    if m:
        date_like = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}%"
        conds.append(NonpenPlan.receive_time.like(date_like) & (NonpenPlan.ticket_seq == int(m.group(2))))
    return or_(*conds)


def plan_search_condition(search: str):
    """渗透测试工单搜索：测试系统 / 所属部门 / 测试类型 / 工单ID（手动指定值，
    或 YYYYMMDD-N 自动编号的日期+序号组合）。站内列表与开放 API 共用。"""
    pat = f"%{search}%"
    conds = [
        TestingPlan.system_name.ilike(pat),
        TestingPlan.department.ilike(pat),
        TestingPlan.test_type.ilike(pat),
        TestingPlan.ticket_id_manual.ilike(pat),
        TestingPlan.receive_time.ilike(pat),
        func.replace(TestingPlan.receive_time, "-", "").ilike(pat),
        func.cast(TestingPlan.ticket_seq, String).ilike(pat),
    ]
    # 完整工单ID匹配：YYYYMMDD-N（如 20260727-1）→ 手动指定值本身，或自动编号的日期+当日序号组合
    m = re.fullmatch(r"(\d{8})-(\d+)", search)
    if m:
        date_like = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}%"
        conds.append(
            TestingPlan.receive_time.like(date_like) & (TestingPlan.ticket_seq == int(m.group(2)))
        )
    return or_(*conds)


# 「当前可测试」判定所用状态：初测中 / 提请复测 / 复测中（测试人视角的进行中状态）
_TESTER_ACTIVE_STATUSES = [
    PlanStatus.TESTING, PlanStatus.RETEST_APPLY, PlanStatus.RETESTING,
]


def _append_date_range(cond: list, col, date_from: str, date_to: str) -> None:
    """日期串字段的范围筛选（YYYY-MM-DD 字符串直接比较）。

    上界需先排除空串：空值的字符串比较恒小于任意日期串，不排除会被误纳入结果。
    """
    if date_from:
        cond.append(col >= date_from)
    if date_to:
        cond.append(col != "")
        cond.append(col <= date_to)


def _append_tester_scope(cond: list, tester_id: int | None, unclaimed: bool) -> None:
    """测试人相关筛选（tester_id / unclaimed 三态，二者同开时为并集）。"""
    if tester_id is None:
        if unclaimed:
            cond.append(
                ~exists().where(testing_plan_testers.c.testing_plan_id == TestingPlan.id)
            )
        return
    assigned = exists().where(
        testing_plan_testers.c.testing_plan_id == TestingPlan.id,
        testing_plan_testers.c.user_id == tester_id,
    )
    if unclaimed:
        # 并集：当前可测试系统 OR 无人认领（与其它筛选条件保持 AND）
        cond.append(
            or_(
                and_(TestingPlan.status.in_(_TESTER_ACTIVE_STATUSES), assigned),
                ~exists().where(testing_plan_testers.c.testing_plan_id == TestingPlan.id),
            )
        )
    else:
        cond.append(TestingPlan.status.in_(_TESTER_ACTIVE_STATUSES))
        cond.append(assigned)


def plan_conditions(
    search: str = "",
    status: int | None = None,
    test_type: str = "",
    department: str = "",
    receive_from: str = "",
    receive_to: str = "",
    first_test_from: str = "",
    first_test_to: str = "",
    tester_id: int | None = None,
    unclaimed: bool = False,
    pending: bool = False,
) -> list:
    """测试计划筛选条件，供列表/统计/导出/结论输出共用。receive_time / first_test_done_time
    均为 YYYY-MM-DD 字符串，直接比较。

    tester_id 非空时过滤「当前可测试系统」：当前用户为测试人且状态为初测中/提请复测/复测中。
    unclaimed 为真时过滤「无人认领的测试」：测试人员列表为空。
    pending 为真时过滤「待办流程」：状态为未测试/初测中/复测中。
    两个快捷模式同时启用时按并集处理：满足任一条件的记录均展示。
    """
    cond: list = []
    if search:
        cond.append(plan_search_condition(search))
    if status is not None:
        cond.append(TestingPlan.status == status)
    if pending:
        # 待办流程：未测试 / 初测中 / 复测中
        cond.append(
            TestingPlan.status.in_([
                PlanStatus.UNTESTED, PlanStatus.TESTING, PlanStatus.RETESTING,
            ])
        )
    if test_type:
        cond.append(TestingPlan.test_type == test_type)
    if department:
        cond.append(TestingPlan.department == department)
    _append_date_range(cond, TestingPlan.receive_time, receive_from, receive_to)
    _append_date_range(cond, TestingPlan.first_test_done_time, first_test_from, first_test_to)
    _append_tester_scope(cond, tester_id, unclaimed)
    return cond


# 可筛选字段白名单：(列名, 字段类型, 是否为 DateTime 列)。日期字符串字段默认 "" 表示空，
# DateTime 列默认 NULL，数字字段默认 0。ticket_id / testers / *_count 为派生/关联字段，单独处理。
PLAN_FILTER_FIELDS: dict[str, tuple[str, str, bool]] = {
    "id": ("id", "number", False),
    "plan_name": ("plan_name", "text", False),
    "system_name": ("system_name", "text", False),
    "test_type": ("test_type", "text", False),
    "department": ("department", "text", False),
    "status": ("status", "enum", False),
    "ticket_id": ("ticket_id", "text", False),  # 派生字段：手动指定或 receive_time+ticket_seq 生成
    "ticket_time": ("ticket_time", "date", False),
    "receive_time": ("receive_time", "date", False),
    "first_test_done_time": ("first_test_done_time", "date", False),
    "retest_notice_time": ("retest_notice_time", "date", False),
    "retest_done_time": ("retest_done_time", "date", False),
    "est_mandays": ("est_mandays", "number", False),
    "actual_mandays": ("actual_mandays", "number", False),
    "stat_critical": ("stat_critical", "number", False),
    "stat_high": ("stat_high", "number", False),
    "stat_medium": ("stat_medium", "number", False),
    "stat_low": ("stat_low", "number", False),
    "testers": ("testers", "text", False),  # 测试人员：多对多姓名/用户名匹配
    "vul_count": ("vul_count", "number", False),  # 关联漏洞计数
    "report_count": ("report_count", "number", False),  # 关联报告计数
    "retest_round_count": ("retest_round_count", "number", False),  # 复测轮数
    "create_time": ("create_time", "date", True),
    "update_time": ("update_time", "date", True),
}


def _ticket_id_filter_expr(op: str, value) -> object:
    """工单ID为派生字段：手动指定值优先，否则由 receive_time(YYYY-MM-DD) + ticket_seq 生成 YYYYMMDD-N。"""
    sv = str(value) if value is not None else ""
    m = re.fullmatch(r"(\d{8})-(\d+)", sv)
    date_like = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}%" if m else None

    def _eq():
        conds = [TestingPlan.ticket_id_manual == sv]
        if date_like:
            conds.append(and_(
                TestingPlan.receive_time.like(date_like),
                TestingPlan.ticket_seq == int(m.group(2)),
            ))
        return or_(*conds)

    if op == "eq":
        return _eq()
    if op == "ne":
        return ~_eq()
    if op in ("contains", "not_contains"):
        expr = or_(
            TestingPlan.ticket_id_manual.ilike(f"%{sv}%"),
            TestingPlan.receive_time.ilike(f"%{sv}%"),
            func.replace(TestingPlan.receive_time, "-", "").ilike(f"%{sv}%"),
            func.cast(TestingPlan.ticket_seq, String).ilike(f"%{sv}%"),
        )
        return expr if op == "contains" else ~expr
    if op == "starts_with":
        if len(sv) >= 8 and sv[:8].isdigit():
            d = f"{sv[:4]}-{sv[4:6]}-{sv[6:8]}"
            return or_(
                TestingPlan.ticket_id_manual.ilike(f"{sv}%"),
                TestingPlan.receive_time.like(f"{d}%"),
            )
        return or_(
            TestingPlan.ticket_id_manual.ilike(f"{sv}%"),
            TestingPlan.receive_time.like(f"{sv}%"),
        )
    if op == "ends_with":
        return or_(
            TestingPlan.ticket_id_manual.ilike(f"%{sv}"),
            func.cast(TestingPlan.ticket_seq, String).ilike(f"%{sv}"),
        )
    if op in ("is_empty", "is_not_empty"):
        empty = (TestingPlan.ticket_id_manual == "") & (TestingPlan.receive_time == "")
        return empty if op == "is_empty" else ~empty
    raise HTTPException(400, f"工单ID字段不支持操作符：{op}")


def _testers_filter_expr(op: str, value) -> object:
    """测试人员筛选：多对多关联 users 表，按姓名/用户名模糊匹配。"""
    if op in ("is_empty", "is_not_empty"):
        sub = exists().where(testing_plan_testers.c.testing_plan_id == TestingPlan.id)
        return ~sub if op == "is_empty" else sub
    sv = str(value) if value is not None else ""
    pat = f"%{sv}%"
    if op == "starts_with":
        pat = f"{sv}%"
    elif op == "ends_with":
        pat = f"%{sv}"
    sub = exists().where(
        testing_plan_testers.c.testing_plan_id == TestingPlan.id,
        testing_plan_testers.c.user_id == User.id,
        or_(User.realname.ilike(pat), User.username.ilike(pat)),
    )
    if op in ("eq", "contains", "starts_with", "ends_with"):
        return sub
    if op in ("ne", "not_contains"):
        return ~sub
    raise HTTPException(400, f"测试人员字段不支持操作符：{op}")


def _plan_count_expr(field: str, op: str, value) -> object:
    """关联计数筛选：关联漏洞数 / 关联报告数 / 复测轮数，通过相关子查询比较。"""
    if field == "vul_count":
        sub = select(func.count(Vul.id)).where(Vul.testing_plan_id == TestingPlan.id).scalar_subquery()
    elif field == "report_count":
        sub = select(func.count(Report.id)).where(Report.testing_plan_id == TestingPlan.id).scalar_subquery()
    else:
        sub = select(func.count(TestingPlanRetestRound.id)).where(
            TestingPlanRetestRound.plan_id == TestingPlan.id
        ).scalar_subquery()
    if op in ("is_empty", "is_not_empty"):
        empty = sub == 0
        return empty if op == "is_empty" else ~empty
    v = to_float(value) if not isinstance(value, (int, float)) else float(value)
    if op == "eq":
        return sub == v
    if op == "ne":
        return sub != v
    if op == "gt":
        return sub > v
    if op == "gte":
        return sub >= v
    if op == "lt":
        return sub < v
    if op == "lte":
        return sub <= v
    if op == "between":
        lo, hi = split_range(value)
        if lo in (None, "") or hi in (None, ""):
            raise HTTPException(400, "区间筛选需要填写完整的起止值")
        return and_(sub >= to_float(lo), sub <= to_float(hi))
    raise HTTPException(400, f"计数字段不支持操作符：{op}")


def plan_filters_condition(filters: str) -> list:
    """解析聚合筛选 JSON（rules + 规则间 and/or 连接 + 单规则 not 取反），返回与现有条件 AND 的条件列表。

    请求格式示例：
        {"rules": [
            {"field": "status", "op": "eq", "value": 20, "not": false, "connector": "and"},
            {"field": "system_name", "op": "contains", "value": "商城", "not": true, "connector": "or"},
        ]}
    rules 按顺序组合：首条规则的 connector 忽略，其余规则的 connector 表示其与上一条之间的逻辑。
    """
    expr = None
    for r in parse_filter_rules(filters):
        if not isinstance(r, dict):
            continue
        field = str(r.get("field", ""))
        op = str(r.get("op", ""))
        if op not in ALLOWED_FILTER_OPS:
            raise HTTPException(400, f"不支持的操作符：{op}")
        if field not in PLAN_FILTER_FIELDS:
            raise HTTPException(400, f"不支持的筛选字段：{field}")
        _, ftype, is_datetime = PLAN_FILTER_FIELDS[field]
        if field == "ticket_id":
            cond = _ticket_id_filter_expr(op, r.get("value"))
        elif field == "testers":
            cond = _testers_filter_expr(op, r.get("value"))
        elif field in ("vul_count", "report_count", "retest_round_count"):
            cond = _plan_count_expr(field, op, r.get("value"))
        else:
            cond = build_filter_expr(
                getattr(TestingPlan, PLAN_FILTER_FIELDS[field][0]), ftype, is_datetime, op, r.get("value")
            )
        if r.get("not"):
            cond = ~cond
        expr = combine_rules(expr, cond, str(r.get("connector") or "and").lower())
    return [expr] if expr is not None else []


def _month_range(start: str, end: str) -> list[str]:
    """由 YYYY-MM-DD 起止生成 YYYY-MM 月份序列（含首尾，上限 120 个月）。"""
    try:
        y1, m1 = int(start[:4]), int(start[5:7])
        y2, m2 = int(end[:4]), int(end[5:7])
    except (ValueError, IndexError):
        return []
    months: list[str] = []
    y, m = y1, m1
    while (y, m) <= (y2, m2) and len(months) < 120:
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


async def _stats_by_status(session: AsyncSession, cond: list) -> list:
    """按状态分组的 (status, count) 列表（工单多维度统计的基础数据）。"""
    return (
        await session.execute(
            select(TestingPlan.status, func.count(TestingPlan.id))
            .where(*cond)
            .group_by(TestingPlan.status)
        )
    ).all()


async def _count_retest_rounds(session: AsyncSession, cond: list) -> int:
    """筛选结果对应的复测轮次总数。"""
    return (
        await session.execute(
            select(func.count(TestingPlanRetestRound.id)).where(
                TestingPlanRetestRound.plan_id.in_(select(TestingPlan.id).where(*cond))
            )
        )
    ).scalar_one()


async def _sum_amount(session: AsyncSession, column, cond: list, extra=None) -> float:
    """按条件求和（空集为 0）；`extra` 为可选附加条件（如「仅未测试状态」）。"""
    stmt = select(func.coalesce(func.sum(column), 0.0)).where(*cond)
    if extra is not None:
        stmt = stmt.where(extra)
    return float((await session.execute(stmt)).scalar_one())


def _month_buckets(receive_from: str, receive_to: str) -> dict[str, int]:
    """按月分桶容器：给定统计区间取区间月份，否则取最近 12 个月。"""
    months = _month_range(receive_from, receive_to) if receive_from and receive_to else []
    if not months:
        now = tznow()
        months = sorted(
            {(now.replace(day=1) - timedelta(days=30 * i)).strftime("%Y-%m") for i in range(12)}
        )
    return {m: 0 for m in months}


async def _vulns_by_month(
    session: AsyncSession, cond: list, receive_from: str, receive_to: str
) -> list[dict]:
    """筛选后工单关联漏洞按提交月份聚合（应用层聚合，规避方言差异）。"""
    monthly = _month_buckets(receive_from, receive_to)
    submit_rows = (
        await session.execute(
            select(Vul.submit_time).where(
                Vul.testing_plan_id.in_(select(TestingPlan.id).where(*cond))
            )
        )
    ).scalars().all()
    for submit_time in submit_rows:
        if submit_time is None:
            continue
        key = submit_time.strftime("%Y-%m")
        if key in monthly:
            monthly[key] += 1
    return [{"month": m, "count": c} for m, c in monthly.items()]


async def compute_plan_stats(
    session: AsyncSession, cond: list, receive_from: str, receive_to: str
) -> dict:
    """按筛选条件计算测试计划多维度统计，供 stats 端点与导出汇总共用。"""
    by_status_rows = await _stats_by_status(session, cond)
    total_plans = sum(c for _, c in by_status_rows)
    retest_done_plans = sum(c for s, c in by_status_rows if s == PlanStatus.RETEST_DONE)
    # 初测次数：达到「初测中」及之后状态的计划各记一次初测
    first_test_count = sum(c for s, c in by_status_rows if s >= PlanStatus.TESTING)

    est_mandays_total = await _sum_amount(session, TestingPlan.est_mandays, cond)
    actual_mandays_total = await _sum_amount(session, TestingPlan.actual_mandays, cond)
    # 剩余预估人天：仅统计未测试状态计划的预估人天之和
    remaining_est_mandays = await _sum_amount(
        session, TestingPlan.est_mandays, cond, TestingPlan.status == PlanStatus.UNTESTED
    )
    retest_count = await _count_retest_rounds(session, cond)

    return {
        "total_plans": total_plans,
        "retest_done_plans": retest_done_plans,
        "first_test_count": first_test_count,
        "retest_count": retest_count,
        "total_test_count": first_test_count + retest_count,
        "est_mandays_total": round(est_mandays_total, 2),
        "actual_mandays_total": round(actual_mandays_total, 2),
        "remaining_est_mandays": round(remaining_est_mandays, 2),
        "by_status": [
            {"status": s, "name": TESTING_PLAN_STATUS.get(s, str(s)), "count": c}
            for s, c in sorted(by_status_rows)
        ],
        "vulns_by_month": await _vulns_by_month(session, cond, receive_from, receive_to),
    }


def _rectify_state(status: int) -> str:
    """整改状态文案：测试通过 = 未发现安全风险；复测完成 = 已完成整改；其余 = 整改中。"""
    if status == PlanStatus.PASSED:
        return "未发现安全风险"
    if status == PlanStatus.RETEST_DONE:
        return "已完成整改"
    return "整改中"


def _plan_vuln_count(plan, linked_count: dict[int, int]) -> int:
    """工单漏洞数：有真实关联漏洞取实际计数，否则回退手填 stat_* 之和（与 stats_service 口径一致）。"""
    if plan.id in linked_count:
        return linked_count[plan.id]
    return plan.stat_critical + plan.stat_high + plan.stat_medium + plan.stat_low


def _conclusion_summary(
    *,
    departments: int,
    systems: int,
    vuln_systems: int,
    vulns: int,
    safe_systems: int,
    fixed_systems: int,
    fixing_systems: int,
) -> str:
    """结论文字（口径与需求确认一致，措辞与顺序勿改）。"""
    return (
        f"业务系统方面，统计周期内发现{departments}个部门{systems}个系统的渗透测试，"
        f"共发现{vuln_systems}个系统存在{vulns}个漏洞，{safe_systems}个系统未发现安全风险。"
        f"目前{fixed_systems}个系统已完成整改，{fixing_systems}个系统整改中。"
        "请相关部门尽快完成漏洞修复并提交复测。具体漏洞情况详见附件。"
    )


async def _conclusion_aggregate(session: AsyncSession, cond: list) -> dict:
    """取工单并按筛选条件聚合结论所需的行数据与计数。"""
    plans = (
        await session.execute(
            select(TestingPlan).where(*cond).order_by(
                TestingPlan.receive_time.desc(), TestingPlan.ticket_seq.desc(), TestingPlan.id.desc(),
            )
        )
    ).scalars().all()
    linked_rows = (
        await session.execute(
            select(Vul.testing_plan_id, func.count(Vul.id))
            .where(Vul.testing_plan_id.in_(select(TestingPlan.id).where(*cond)))
            .group_by(Vul.testing_plan_id)
        )
    ).all()
    linked_count = {pid: c for pid, c in linked_rows}

    departments: set[str] = set()
    rows: list[dict] = []
    total_vulns = safe_systems = fixed_systems = 0
    for p in plans:
        department = p.department or "未填写"
        departments.add(department)
        vul_count = _plan_vuln_count(p, linked_count)
        total_vulns += vul_count
        if p.status == PlanStatus.PASSED:
            safe_systems += 1
        elif p.status == PlanStatus.RETEST_DONE:
            fixed_systems += 1
        rows.append({
            "ticket_id": p.ticket_id,
            "department": department,
            "system_name": p.system_name,
            "vuln_count": vul_count,
            "test_type": p.test_type,
            "rectify_state": _rectify_state(p.status),
        })
    return {
        "rows": rows,
        "departments": len(departments),
        "systems": len(rows),
        "vulns": total_vulns,
        "safe_systems": safe_systems,
        "fixed_systems": fixed_systems,
    }


async def compute_conclusion(session: AsyncSession, cond: list) -> dict:
    """结论性输出：按筛选条件聚合部门/系统/漏洞/整改状态，生成结论文字与附件行数据。

    口径（与需求确认一致）：
    - 部门数 = 筛选结果 department 去重；系统数 = 工单数；
    - 漏洞数 = 工单关联漏洞真实数，无关联则用手填 stat_* 之和（与 stats_service 一致）；
    - 未发现安全风险 = 状态测试通过(PASSED)；已完成整改 = 复测完成(RETEST_DONE)；
    - 整改中 = 其余（非通过且非复测完成）。
    """
    agg = await _conclusion_aggregate(session, cond)
    systems = agg["systems"]
    vuln_systems = systems - agg["safe_systems"]
    fixing_systems = systems - agg["fixed_systems"] - agg["safe_systems"]
    return {
        "summary": _conclusion_summary(
            departments=agg["departments"],
            systems=systems,
            vuln_systems=vuln_systems,
            vulns=agg["vulns"],
            safe_systems=agg["safe_systems"],
            fixed_systems=agg["fixed_systems"],
            fixing_systems=fixing_systems,
        ),
        "departments": agg["departments"],
        "systems": systems,
        "vuln_systems": vuln_systems,
        "vulns": agg["vulns"],
        "safe_systems": agg["safe_systems"],
        "fixed_systems": agg["fixed_systems"],
        "fixing_systems": fixing_systems,
        "rows": agg["rows"],
    }
