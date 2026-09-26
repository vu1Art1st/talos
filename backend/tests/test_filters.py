"""聚合筛选引擎单元测试：条件分组/嵌套解析、历史扁平格式兼容、结构限制与空分组语义，
以及 P0-1 的 DateTime 列日期区间口径（半开区间 + 绑定类型守卫）。

只覆盖纯结构逻辑（不依赖数据库）：表达式在真实查询上的正确性由 API 级用例
`tests/api/test_api_plans.py::test_testing_plan_nested_filters` 与
`test_testing_plan_datetime_filters` 端到端验证。
"""
import json
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import DateTime, String, column
from sqlalchemy.dialects import postgresql

from app.core.filters import (
    MAX_FILTER_DEPTH,
    MAX_FILTER_RULES,
    build_filter_expr,
    build_tree_condition,
    count_filter_rules,
    parse_filter_tree,
)


def rule(field: str, op: str, value=None, *, not_=False, connector: str | None = None) -> dict:
    r = {"field": field, "op": op, "value": value, "not": not_}
    if connector:
        r["connector"] = connector
    return r


def group(*children, logic: str = "and", not_: bool = False) -> dict:
    return {"logic": logic, "not": not_, "children": list(children)}


def parse(payload) -> dict | None:
    return parse_filter_tree(payload if isinstance(payload, str) else json.dumps(payload))


# ---------- 解析与规范化 ----------


def test_parse_nested_tree_keeps_hierarchy_and_defaults():
    """v2 嵌套结构原样保留层级；缺失的 not / kind 补齐默认值。"""
    tree = parse(group(
        rule("receive_time", "gt", "2026-01-01"),
        group(rule("status", "eq", 30), rule("status", "eq", 40), logic="or"),
    ))
    assert tree["kind"] == "group" and tree["logic"] == "and" and tree["not"] is False
    first, second = tree["children"]
    assert first == {"kind": "rule", "field": "receive_time", "op": "gt", "value": "2026-01-01", "not": False}
    assert second["kind"] == "group" and second["logic"] == "or" and second["not"] is False
    assert [c["field"] for c in second["children"]] == ["status", "status"]
    assert count_filter_rules(tree) == 3


def test_parse_legacy_flat_rules_fold_left_assoc():
    """历史扁平格式按左结合折叠：a AND b OR c ≡ (a AND b) OR c；同逻辑连续则平铺。"""
    tree = parse({"rules": [
        rule("a", "eq", 1),
        rule("b", "eq", 2, connector="or"),
        rule("c", "eq", 3),
    ]})
    assert tree["logic"] == "and"
    left, tail = tree["children"]
    assert left["logic"] == "or" and [c["field"] for c in left["children"]] == ["a", "b"]
    assert tail["field"] == "c"

    flat = parse({"rules": [rule("a", "eq", 1), rule("b", "eq", 2), rule("c", "eq", 3)]})
    assert flat["logic"] == "and"
    assert [c["field"] for c in flat["children"]] == ["a", "b", "c"]


def test_parse_accepts_bare_rule_array_and_group_kind():
    """兼容裸数组与显式 kind=group 两种写法（前端与脚本都可能给出）。"""
    assert parse([rule("a", "eq", 1)])["children"][0]["field"] == "a"
    tree = parse({"kind": "group", "logic": "or", "children": [rule("a", "eq", 1)]})
    assert tree["logic"] == "or"


def test_parse_empty_or_invalid_children_returns_none():
    """空输入 / 空分组 / 非法子项被跳过 → 无有效条件时返回 None（不追加任何筛选）。"""
    assert parse_filter_tree("") is None
    assert parse({}) is None
    assert parse({"logic": "and", "children": []}) is None
    assert parse({"rules": []}) is None
    assert parse({"logic": "and", "children": ["x", 3, None]}) is None
    # 混入非法子项时只丢弃该项，合法条件保留
    tree = parse({"logic": "and", "children": ["x", rule("a", "eq", 1)]})
    assert count_filter_rules(tree) == 1


@pytest.mark.parametrize("payload", [
    "not-json",
    "123",
    {"logic": "xor", "children": [rule("a", "eq", 1)]},
    {"logic": "and", "children": [rule("", "eq", 1)]},
    {"logic": "and", "children": [rule("a", "unknown_op", 1)]},
    {"logic": "and", "children": {"field": "a"}},
])
def test_parse_rejects_invalid_structures(payload):
    with pytest.raises(HTTPException) as exc:
        parse(payload)
    assert exc.value.status_code == 400


def test_parse_enforces_depth_and_rule_limits():
    """深嵌套与超量规则必须被拒（防止恶意结构放大查询代价）。"""
    deep = rule("a", "eq", 1)
    for _ in range(MAX_FILTER_DEPTH):
        deep = group(deep)
    assert parse(deep) is not None
    with pytest.raises(HTTPException) as exc:
        parse(group(deep))
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        parse(group(*[rule("a", "eq", i) for i in range(MAX_FILTER_RULES + 1)]))
    assert exc.value.status_code == 400


# ---------- 表达式构造 ----------


def leaf(field: str, op: str, value):
    """最小 leaf 构造器：仅支持 eq / gt，用于校验树形组合与取反。"""
    col = column(field)
    if op == "eq":
        return col == value
    if op == "gt":
        return col > value
    raise HTTPException(400, f"不支持的字段或操作符：{field}/{op}")


def sql(node) -> str:
    expr = build_tree_condition(node, leaf)
    return str(expr.compile(compile_kwargs={"literal_binds": True}))


def test_build_condition_respects_group_boundaries():
    """「时间晚于 X 且（状态 Y 或 Z）」必须保留括号（分组边界 = 优先级）。"""
    tree = parse(group(
        rule("receive_time", "gt", "2026-01-01"),
        group(rule("status", "eq", 30), rule("status", "eq", 40), logic="or"),
    ))
    assert sql(tree) == (
        "receive_time > '2026-01-01' AND (status = 30 OR status = 40)"
    )


def test_build_condition_applies_node_level_not():
    """规则级 not 与分组级 not 分别作用于自身节点；分组取反整体加括号。"""
    tree = parse(group(
        rule("a", "eq", 1, not_=True),
        group(rule("b", "eq", 2), rule("c", "eq", 3), logic="or", not_=True),
    ))
    assert sql(tree) == "a != 1 AND NOT (b = 2 OR c = 3)"


def test_build_condition_ignores_empty_groups():
    """空分组（含仅含空分组的父分组）不参与组合；整体为空返回 None。"""
    tree = parse(group(rule("a", "eq", 1), group()))
    assert sql(tree) == "a = 1"
    # 顶层只有一个空分组：解析阶段即判定为「无有效条件」
    assert parse(group(group())) is None
    # 取反不会把「空条件」变成恒真：构造层直接忽略该分组
    assert build_tree_condition({"kind": "group", "logic": "and", "not": True, "children": []}, leaf) is None


# ---------- P0-1：DateTime 列日期区间口径 ----------


def dt_col():
    return column("create_time", DateTime())


def dt_compiled(op: str, value):
    """按 PostgreSQL 方言编译 DateTime 字段筛选表达式（只读编译，不连库）。"""
    expr = build_filter_expr(dt_col(), "date", True, op, value)
    return expr.compile(dialect=postgresql.dialect())


DT_OPS = [
    ("eq", "2026-01-15"),
    ("ne", "2026-01-15"),
    ("gt", "2026-01-15"),
    ("gte", "2026-01-15"),
    ("lt", "2026-01-15"),
    ("lte", "2026-01-15"),
    ("between", ["2026-01-15", "2026-01-31"]),
]


@pytest.mark.parametrize("op,value", DT_OPS)
def test_datetime_filter_binds_datetime_and_never_calls_date(op, value):
    """P0-1 守卫：DateTime 列不得出现 `date(...)`，且所有绑定必须是 DateTime。

    背景：`func.date(col) >= '2026-09-14'` 会把日期串按 VARCHAR 绑定，PostgreSQL 无
    `date >= character varying` 算子（asyncpg 抛 UndefinedFunctionError → 线上 500）。
    """
    compiled = dt_compiled(op, value)
    assert {type(b.type).__name__ for b in compiled.binds.values()} == {"DateTime"}
    assert "date(" not in str(compiled)


def test_datetime_filter_boundaries_are_half_open_per_day():
    """边界口径：一律 `[当日 00:00, 次日 00:00)`；覆盖当日零点、当日最后一秒、跨月与闰日。"""
    def lit(op, value):
        return str(build_filter_expr(dt_col(), "date", True, op, value)
                   .compile(compile_kwargs={"literal_binds": True}))

    # eq：整天区间；「当日最后一秒」（次日 00:00 前一微秒）含在内，次日零点不含
    assert lit("eq", "2026-01-15") == (
        "create_time IS NOT NULL AND create_time >= '2026-01-15 00:00:00' "
        "AND create_time < '2026-01-16 00:00:00'"
    )
    # 跨月：1 月末日的次日为 2 月 1 日
    assert "create_time < '2026-02-01 00:00:00'" in lit("eq", "2026-01-31")
    # 闰日：2024-02-29 可解析，次日为 3 月 1 日
    assert "create_time < '2024-03-01 00:00:00'" in lit("eq", "2024-02-29")
    # gt/lt 为严格单边（区别只在用哪一端）
    assert lit("gt", "2026-01-15") == "create_time >= '2026-01-16 00:00:00'"
    assert lit("gte", "2026-01-15") == "create_time >= '2026-01-15 00:00:00'"
    assert lit("lt", "2026-01-15") == "create_time < '2026-01-15 00:00:00'"
    assert lit("lte", "2026-01-15") == "create_time < '2026-01-16 00:00:00'"
    # ne 保持三值逻辑：NULL 行不命中
    assert lit("ne", "2026-01-15") == (
        "create_time IS NOT NULL AND (create_time < '2026-01-15 00:00:00' "
        "OR create_time >= '2026-01-16 00:00:00')"
    )
    # between 为闭开区间 [起始日, 结束日次日)
    assert lit("between", ["2026-01-15", "2026-01-31"]) == (
        "create_time IS NOT NULL AND create_time >= '2026-01-15 00:00:00' "
        "AND create_time < '2026-02-01 00:00:00'"
    )


def test_datetime_day_bounds_and_illegal_input():
    """`day_bounds` 是唯一日期解析入口：跨月/闰日正确，空值与非法日期一律 400。"""
    from app.core.filters import day_bounds

    assert day_bounds("2026-01-31") == (
        datetime(2026, 1, 31), datetime(2026, 2, 1)
    )
    assert day_bounds("2024-02-29") == (datetime(2024, 2, 29), datetime(2024, 3, 1))
    # 与 plan_query 的半开区间口径同源（次日 = 当日 + 1 天）
    assert day_bounds("2026-09-19")[1] == day_bounds("2026-09-19")[0] + timedelta(days=1)

    for bad in ("", None, "  ", "2026-1-1", "2026/01/01", "2025-02-29", "2026-13-01", "not-a-date"):
        with pytest.raises(HTTPException) as exc:
            day_bounds(bad)
        assert exc.value.status_code == 400


def test_datetime_filter_rejects_illegal_and_incomplete_values():
    """非法日期与不完整区间必须 400（不得生成错误 SQL 或静默返回空）。"""
    for op, value in [
        ("eq", "2026-02-30"), ("gt", "not-a-date"), ("lte", ""), ("gte", None),
        ("between", ["2026-01-01", ""]), ("between", "single"),
        ("unknown_op", "2026-01-01"),
    ]:
        with pytest.raises(HTTPException) as exc:
            build_filter_expr(dt_col(), "date", True, op, value)
        assert exc.value.status_code == 400


def test_datetime_is_empty_operators_check_null_only():
    """空值判定：DateTime 列的「为空」只看 NULL（区别于日期字符串列的空串）。"""
    def lit(op):
        return str(build_filter_expr(dt_col(), "date", True, op, None)
                   .compile(compile_kwargs={"literal_binds": True}))

    assert lit("is_empty") == "create_time IS NULL"
    assert lit("is_not_empty") == "create_time IS NOT NULL"


def test_date_string_filter_keeps_string_semantics():
    """冻结基线：日期**字符串**列（is_datetime=False）继续按字典序直接比较，绑定为 VARCHAR。"""
    col = column("receive_time", String())

    def lit(op, value):
        expr = build_filter_expr(col, "date", False, op, value)
        compiled = expr.compile(dialect=postgresql.dialect())
        assert "DateTime" not in {type(b.type).__name__ for b in compiled.binds.values()}
        return str(expr.compile(compile_kwargs={"literal_binds": True}))

    assert lit("gt", "2026-01-01") == "receive_time > '2026-01-01'"
    assert lit("gte", "2026-01-01") == "receive_time >= '2026-01-01'"
    assert lit("lt", "2026-01-01") == (
        "receive_time IS NOT NULL AND receive_time != '' AND receive_time < '2026-01-01'"
    )
    assert lit("lte", "2026-01-01") == (
        "receive_time IS NOT NULL AND receive_time != '' AND receive_time <= '2026-01-01'"
    )
    assert lit("between", ["2026-01-01", "2026-01-31"]) == (
        "receive_time IS NOT NULL AND receive_time != '' "
        "AND receive_time >= '2026-01-01' AND receive_time <= '2026-01-31'"
    )
