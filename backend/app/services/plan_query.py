"""测试计划查询支撑：固定参数筛选、聚合筛选（filters JSON）与多维度统计。

列表 / 统计 / 导出三个入口共用的条件拼装都集中在此，路由层只做参数编排。
聚合筛选的通用表达式构造在 core/filters.py，本模块补充 TestingPlan 特有的
派生字段（工单ID、测试人员多对多、关联计数）。
关键词搜索（plan_search_condition / nonpen_search_condition）与聚合筛选的
工单ID表达式（_ticket_id_filter_expr）口径一致：手动指定值优先，否则由
receive_time(YYYY-MM-DD) + ticket_seq 派生 YYYYMMDD-N；自动编号一律经
`_auto_ticket_id_cond` 构造（要求 ticket_id_manual 为空），与
`ticket_service.check_ticket_id_unique` 的占用口径严格一致，避免幽灵序号误命中。
"""
import re
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import String, and_, exists, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import NONPEN_ITEMS, TESTING_PLAN_STATUS, PlanStatus, VulStatus
from app.core.filters import (
    build_filter_expr,
    build_tree_condition,
    parse_filter_tree,
    split_range,
    to_float,
)
from app.services.plan_service import RETEST_TITLE_MARK
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


def _auto_ticket_id_cond(model, date_like: str, seq: int):
    """自动编号（`YYYYMMDD-N`）的完整命中口径：**仅「纯自动」记录参与**。

    `ticket_id_manual` 非空的记录，即使底层 `ticket_seq` 残留旧值（手动改号后序号不清零，
    见 `ticket_service.assign_ticket_seq` 的提前返回），也**不得**被
    `receive_time + ticket_seq` 命中——否则「先自动得到 20260730-1、后手工改为别的编号」
    的记录会与真正显示 20260730-1 的记录一起被搜出来（一次搜索返回两条，2026-09-22 实测：
    id=2 手工改为 20260730-2 但 seq 仍为 1，与 id=4 的 20260730-1 同时命中）。

    该守卫与 `ticket_service.check_ticket_id_unique` 的占用口径严格一致：手动指定了编号的
    记录其底层 `ticket_seq` 不再视为占用。
    """
    return and_(
        model.receive_time.like(date_like),
        model.ticket_seq == seq,
        model.ticket_id_manual == "",
    )


# 漏扫基线工单「可进行」判定所用的可测试状态（与 models/special.NonpenPlan.actionable 同口径）
NONPEN_ACTIONABLE_STATUSES = ("not_started", "testing", "retesting")


def nonpen_actionable_condition():
    """漏扫基线工单「仅可进行」的 **SQL 侧** 派生条件（P0-4）。

    为什么必须下推到 SQL：`items` 是 JSON 固定键容器（`constants.NONPEN_ITEMS` =
    baseline/host/web，每键 `{status, first_times, retest_times}`），原实现在 Python 侧用
    `NonpenPlan.actionable` 过滤，只能「取回最多 10000 条 + 应用层过滤再分页」，
    数据量增长后每次请求的读取量与内存都线性放大。

    实现要点：**键名必须内联为字面量，不能用绑定参数**——表达式索引
    `(items -> 'baseline' ->> 'status')` 只有在查询表达式与索引表达式结构完全一致时才会
    被使用，而 `json_extract_path_text(items, $1, $2)` 里的 Param 节点与索引中的 Const
    节点不相等，规划器不会采信该索引。键名来自代码常量（非用户输入），无注入面。
    路径是**两级**：先取测试项对象（`->` 返回 json），再取 status（`->>` 返回文本）。
    口径与 `NonpenPlan.actionable` 属性一致，二者由 `tests/api/test_api_nonpen.py`
    的等价性用例锁定。
    """
    return and_(
        NonpenPlan.items.is_not(None),
        or_(*[
            literal_column(
                f"nonpen_plans.items -> '{key}' ->> 'status'"
            ).in_(NONPEN_ACTIONABLE_STATUSES)
            for key in NONPEN_ITEMS
        ]),
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
        conds.append(_auto_ticket_id_cond(NonpenPlan, date_like, int(m.group(2))))
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
        conds.append(_auto_ticket_id_cond(TestingPlan, date_like, int(m.group(2))))
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


def _day_start(value: str) -> datetime:
    """`YYYY-MM-DD` → 当天 00:00（naive 本地时间，与库内 DateTime 存储口径一致）。"""
    return datetime.fromisoformat(f"{value}T00:00:00")


def _datetime_date_range(col, start: datetime | None, end: datetime | None):
    """DateTime 列的**日期**区间：`[开始日 00:00, 结束日次日 00:00)` 半开区间。

    **禁止改回 `func.date(col) >= '<日期串>'`**：那样日期串会按 VARCHAR 绑定，PostgreSQL
    不存在 `date >= character varying` 算子，asyncpg 直接抛 UndefinedFunctionError
    （2026-09-19 线上四个入口 500：`operator does not exist: date >= character varying`）。
    半开区间同时不在列上套函数，可利用 start_time 等索引。
    """
    conds = [col.is_not(None)]
    if start is not None:
        conds.append(col >= start)
    if end is not None:
        conds.append(col < end)
    return and_(*conds)


def _period_condition(date_from: str, date_to: str):
    """统计周期命中条件：初测完成 / 复测发起 / 复测完成 / 复测报告生成 任一落入周期。

    为什么不能只看完成点（2026-09-19 实测）：`retest_done_time` 与轮次 `done_time` 只在
    **工单全部漏洞闭环**时才写入，回退复测时还会清空（见 `vul_service.sync_plan_retest_state`）。
    仅依赖它们会让「周期内已完成的复测」漏统计（实例：工单 20260721-1 初测完成 7-30、
    复测轮次 9-16 发起且复测报告 9-16 生成，但两个完成点均为空）。

    日期串列（`first_test_done_time` / `retest_notice_time` / `retest_done_time` 为 YYYY-MM-DD 文本）
    按文本比较，上界需先排除空串；轮次与报告为 DateTime 列，按 `_datetime_date_range`
    的日期半开区间比较。
    """
    if not date_from and not date_to:
        return None
    try:
        start = _day_start(date_from) if date_from else None
        end = _day_start(date_to) + timedelta(days=1) if date_to else None
    except ValueError:
        raise HTTPException(400, "统计周期日期格式错误，需为 YYYY-MM-DD")

    def _text_range(col, *, guard_empty: bool = True):
        conds = [col.is_not(None)]
        if date_from:
            conds.append(col >= date_from)
        if date_to:
            if guard_empty:
                conds.append(col != "")
            conds.append(col <= date_to)
        return and_(*conds)

    def _datetime_range(col):
        return _datetime_date_range(col, start, end)

    retest_report = exists().where(
        Report.testing_plan_id == TestingPlan.id,
        Report.title.ilike(f"%{RETEST_TITLE_MARK}%"),
        _datetime_range(Report.create_time),
    )
    return or_(
        _text_range(TestingPlan.first_test_done_time),
        _text_range(TestingPlan.retest_notice_time),
        _text_range(TestingPlan.retest_done_time),
        exists().where(
            TestingPlanRetestRound.plan_id == TestingPlan.id,
            _datetime_range(TestingPlanRetestRound.start_time),
        ),
        exists().where(
            TestingPlanRetestRound.plan_id == TestingPlan.id,
            _datetime_range(TestingPlanRetestRound.done_time),
        ),
        retest_report,
    )


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
    """测试计划筛选条件，供列表/统计/导出/结论输出共用。receive_time 等为 YYYY-MM-DD 字符串，直接比较。

    first_test_from / first_test_to 为**统计周期**起止（参数名沿用历史）：命中口径见
    `_period_condition`（初测完成 / 复测发起 / 复测完成 / 复测报告生成 任一落入周期），
    不再是「初测完成时间」单列过滤，保证周期内完成的复测能被纳入。

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
    period = _period_condition(first_test_from, first_test_to)
    if period is not None:
        cond.append(period)
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
            conds.append(_auto_ticket_id_cond(TestingPlan, date_like, int(m.group(2))))
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


def _plan_leaf_condition(field: str, op: str, value) -> object:
    """单条规则 → 表达式（字段白名单 + 派生/关联字段特化；取反由条件树统一施加）。"""
    if field not in PLAN_FILTER_FIELDS:
        raise HTTPException(400, f"不支持的筛选字段：{field}")
    if field == "ticket_id":
        return _ticket_id_filter_expr(op, value)
    if field == "testers":
        return _testers_filter_expr(op, value)
    if field in ("vul_count", "report_count", "retest_round_count"):
        return _plan_count_expr(field, op, value)
    column, ftype, is_datetime = PLAN_FILTER_FIELDS[field]
    return build_filter_expr(getattr(TestingPlan, column), ftype, is_datetime, op, value)


def plan_filters_condition(filters: str) -> list:
    """聚合筛选 JSON → 条件列表（与固定参数按 AND 组合），支持条件分组与任意嵌套。

    请求格式（v2，推荐）——组内逻辑、整组取反、组间逻辑由嵌套层级显式表达：
        {"logic": "and", "not": false, "children": [
            {"kind": "rule", "field": "receive_time", "op": "gt", "value": "2026-01-01"},
            {"kind": "group", "logic": "or", "not": false, "children": [
                {"kind": "rule", "field": "status", "op": "eq", "value": 30},
                {"kind": "rule", "field": "status", "op": "eq", "value": 40},
            ]},
        ]}
    即「需求接收晚于 2026-01-01 且（状态为初测完成 或 提请复测）」。

    历史扁平格式（{"rules": [...]}，规则间 connector 左结合）继续兼容，解析细节见
    core/filters.parse_filter_tree；空分组被忽略，条件树整体为空时不追加任何条件。
    """
    root = parse_filter_tree(filters)
    if root is None:
        return []
    expr = build_tree_condition(root, _plan_leaf_condition)
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


def _period_text(period_label: str, date_from: str, date_to: str) -> str:
    """结论文字的周期括注：快捷项（本周/本月…）取名称，自定义区间取起止日期，未筛选为「全部时间」。"""
    if period_label:
        return period_label
    if date_from and date_to:
        return f"{date_from} - {date_to}"
    if date_from or date_to:
        return f"{date_from or '不限'} - {date_to or '不限'}"
    return "全部时间"


def _in_period(value: str, date_from: str, date_to: str) -> bool:
    """YYYY-MM-DD 字符串是否落在统计周期内（空值不命中）。"""
    if not value:
        return False
    return (not date_from or value >= date_from) and (not date_to or value <= date_to)


def _ts_in_period(value: datetime | None, date_from: str, date_to: str) -> bool:
    """DateTime 是否落在统计周期内（按本地日期，与 SQL 侧 `_datetime_date_range` 半开区间同口径）。"""
    return value is not None and _in_period(value.date().isoformat(), date_from, date_to)


def _conclusion_summary(agg: dict, period_text: str) -> str:
    """结论文字（2026-09-19 新模板，措辞与顺序勿改）。"""
    names = "、".join(agg["department_names"]) or "无"
    return (
        f"渗透测试方面，统计周期内（{period_text}）共完成{agg['departments']}个部门（{names}）的"
        f"{agg['systems']}个系统测试工作。其中初测完成{agg['first_test_systems']}个系统"
        f"发现{agg['first_test_vulns']}个漏洞。复测完成{agg['retest_systems']}个系统，"
        f"其中{agg['retest_fixed_systems']}个系统已完成整改，"
        f"{agg['retest_unfixed_systems']}个系统未完成整改仍存在漏洞未修复。"
        "请相关部门尽快完成漏洞修复并提交复测。具体漏洞情况详见附件。"
    )


def _conclusion_flags(
    plans: list, rounds: list, retest_reports: list, date_from: str, date_to: str,
) -> dict:
    """按周期口径标记每个命中工单：初测完成 / 复测动作 / 发起复测（口径见 `_period_condition`）。"""
    flags: dict[int, dict[str, bool]] = {}
    for p in plans:
        notice = _in_period(p.retest_notice_time, date_from, date_to)
        flags[p.id] = {
            "first": _in_period(p.first_test_done_time, date_from, date_to),
            "started": notice,
            "retest": notice,
        }
    for plan_id, start_time, done_time in rounds:
        if plan_id not in flags:
            continue
        if _ts_in_period(start_time, date_from, date_to):
            flags[plan_id]["retest"] = True
            flags[plan_id]["started"] = True
        if _ts_in_period(done_time, date_from, date_to):
            flags[plan_id]["retest"] = True
    report_count = 0
    for plan_id, create_time in retest_reports:
        if _ts_in_period(create_time, date_from, date_to):
            report_count += 1
            if plan_id in flags:
                flags[plan_id]["retest"] = True
    return {"flags": flags, "retest_report_count": report_count}


async def _count_vulns_by_plan(
    session: AsyncSession, ids: list[int], *, only_open: bool = False,
) -> dict[int, int]:
    """按工单统计关联漏洞数（`only_open=True` 时只统计未闭环：非已修复/已忽略）。"""
    if not ids:
        return {}
    stmt = select(Vul.testing_plan_id, func.count(Vul.id)).where(Vul.testing_plan_id.in_(ids))
    if only_open:
        stmt = stmt.where(~Vul.status.in_((VulStatus.IGNORED, VulStatus.FIXED)))
    rows = (await session.execute(stmt.group_by(Vul.testing_plan_id))).all()
    return {pid: int(count) for pid, count in rows}


async def _conclusion_aggregate(
    session: AsyncSession, cond: list, date_from: str = "", date_to: str = "",
) -> dict:
    """取命中工单并按统计周期聚合结论所需的行数据与计数（周期口径见 `plan_conditions`）。"""
    plans = (
        await session.execute(
            select(TestingPlan).where(*cond).order_by(
                TestingPlan.receive_time.desc(), TestingPlan.ticket_seq.desc(), TestingPlan.id.desc(),
            )
        )
    ).scalars().all()
    ids = [p.id for p in plans]
    linked_count = await _count_vulns_by_plan(session, ids)
    open_count = await _count_vulns_by_plan(session, ids, only_open=True)
    rounds = (
        await session.execute(
            select(
                TestingPlanRetestRound.plan_id,
                TestingPlanRetestRound.start_time,
                TestingPlanRetestRound.done_time,
            ).where(TestingPlanRetestRound.plan_id.in_(ids))
        )
    ).all()
    retest_reports = (
        await session.execute(
            select(Report.testing_plan_id, Report.create_time).where(
                Report.testing_plan_id.in_(ids),
                Report.title.ilike(f"%{RETEST_TITLE_MARK}%"),
            )
        )
    ).all()
    marked = _conclusion_flags(plans, rounds, retest_reports, date_from, date_to)
    flags = marked["flags"]

    dept_names: list[str] = []
    rows: list[dict] = []
    first_test_systems = first_test_vulns = 0
    retest_systems = retest_fixed = retest_started = 0
    for p in plans:
        department = p.department or "未填写"
        if department not in dept_names:
            dept_names.append(department)
        vul_count = _plan_vuln_count(p, linked_count)
        all_closed = linked_count.get(p.id, 0) > 0 and open_count.get(p.id, 0) == 0
        if flags[p.id]["first"]:
            first_test_systems += 1
            first_test_vulns += vul_count
        if flags[p.id]["retest"]:
            retest_systems += 1
            retest_fixed += 1 if all_closed else 0
        if flags[p.id]["started"]:
            retest_started += 1
        rows.append({
            "ticket_id": p.ticket_id,
            "department": department,
            "system_name": p.system_name,
            "vuln_count": vul_count,
            "test_type": p.test_type,
            "first_test_done_time": p.first_test_done_time,
            "retest_done_time": p.retest_done_time,
            "rectify_state": _rectify_state(p.status),
        })
    return {
        "rows": rows,
        "departments": len(dept_names),
        "department_names": dept_names,
        "systems": len(plans),
        "first_test_systems": first_test_systems,
        "first_test_vulns": first_test_vulns,
        "retest_systems": retest_systems,
        "retest_fixed_systems": retest_fixed,
        "retest_unfixed_systems": retest_systems - retest_fixed,
        "retest_started_systems": retest_started,
        "retest_report_count": marked["retest_report_count"],
    }


async def compute_conclusion(
    session: AsyncSession, cond: list,
    period_label: str = "", date_from: str = "", date_to: str = "",
) -> dict:
    """结论性输出：按统计周期聚合部门/初测/复测/整改情况，生成结论文字与附件行数据。

    口径（2026-09-19 与需求确认一致）：
    - 周期命中 = 初测完成 / 复测发起 / 复测完成 / 复测报告生成 任一落入周期（见 `_period_condition`）；
    - 共完成系统数 = 命中工单数（按工单去重）；部门 = 命中工单 department 去重（空值记「未填写」）；
    - 初测完成系统 = `first_test_done_time` 命中周期的工单；其漏洞数 = 关联漏洞真实数
      （无关联回退手填 stat_* 之和，与 stats_service 一致）；
    - 复测完成系统 = 周期内有复测动作（发起 / 完成 / 复测报告生成）的工单；
      其中「已完成整改」= 该工单全部关联漏洞闭环（已修复/已忽略），其余为未完成整改仍存在漏洞未修复。
    """
    agg = await _conclusion_aggregate(session, cond, date_from, date_to)
    period_text = _period_text(period_label, date_from, date_to)
    return {
        **agg,
        "period_text": period_text,
        "summary": _conclusion_summary(agg, period_text),
    }
