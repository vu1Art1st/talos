"""聚合筛选引擎单元测试：条件分组/嵌套解析、历史扁平格式兼容、结构限制与空分组语义。

只覆盖纯结构逻辑（不依赖数据库）：表达式在真实查询上的正确性由 API 级用例
`tests/api/test_api_plans.py::test_testing_plan_nested_filters` 端到端验证。
"""
import json

import pytest
from fastapi import HTTPException
from sqlalchemy import column

from app.core.filters import (
    MAX_FILTER_DEPTH,
    MAX_FILTER_RULES,
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
