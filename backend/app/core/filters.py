"""聚合筛选通用引擎：按字段类型把「规则 JSON」翻译为 SQLAlchemy 表达式。

与具体模型解耦：调用方提供列对象与字段类型（text/enum/number/date + 是否 DateTime 列），
本模块只负责操作符白名单、区间取值与表达式构造；派生/关联字段（如工单ID、多对多、计数）
由调用方提供 leaf 构造器（`build_tree_condition` 的 `leaf_builder` 参数）后统一组合。

条件结构（v2，支持分组嵌套与「组内 且/或、整体 非、组间 且/或」任意组合）：
    {"logic": "and", "not": false, "children": [
        {"kind": "rule", "field": "receive_time", "op": "gt", "value": "2026-01-01"},
        {"kind": "group", "logic": "or", "not": false, "children": [
            {"kind": "rule", "field": "status", "op": "eq", "value": 30},
            {"kind": "rule", "field": "status", "op": "eq", "value": 40},
        ]},
    ]}
优先级完全由嵌套层级显式表达（先算括号内、再按父级 logic 组合），不存在隐式优先级。
历史扁平格式（`{"rules": [...]}` 或裸数组，规则间 `connector` 左结合）继续兼容，
解析时按左结合语义等价折叠为上述嵌套树。
"""
import json

from fastapi import HTTPException
from sqlalchemy import and_, func

# 规则操作符白名单：所有接入聚合筛选的接口共用同一套语义
ALLOWED_FILTER_OPS = {
    "eq", "ne", "contains", "not_contains", "starts_with", "ends_with",
    "gt", "gte", "lt", "lte", "between", "is_empty", "is_not_empty",
}

# 分组逻辑运算符白名单与结构上限（深嵌套 / 超量规则会放大查询代价，需显式设限）
GROUP_LOGICS = ("and", "or")
MAX_FILTER_DEPTH = 5
MAX_FILTER_RULES = 50


def split_range(value) -> tuple:
    """between 操作符取值：优先 [lo, hi] 数组，兼容 'lo,hi' 字符串。"""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return value[0], value[1]
    if isinstance(value, str) and "," in value:
        a, b = value.split(",", 1)
        return a, b
    raise HTTPException(400, "between 操作符需要两个值（如 [起始值, 结束值]）")


def to_float(text) -> float:
    """宽松数字解析：空值/非法输入归 0，供筛选与 Excel 单元格取数共用。"""
    try:
        return float(text) if text else 0.0
    except (TypeError, ValueError):
        return 0.0


def build_filter_expr(col, ftype: str, is_datetime: bool, op: str, value) -> object:
    """按字段类型构造单字段筛选条件（不含 NOT 取反）。"""
    if op in ("is_empty", "is_not_empty"):
        if ftype == "number":
            empty = col.is_(None) | (col == 0)
        elif is_datetime:
            empty = col.is_(None)
        else:
            empty = col.is_(None) | (col == "")
        return empty if op == "is_empty" else ~empty
    if is_datetime:
        # DateTime 列统一转日期字符串比较，保证跨数据库行为一致
        col = func.date(col)
    if ftype in ("text", "enum"):
        if op == "contains":
            return col.ilike(f"%{value}%")
        if op == "not_contains":
            return ~col.ilike(f"%{value}%")
        if op == "starts_with":
            return col.ilike(f"{value}%")
        if op == "ends_with":
            return col.ilike(f"%{value}")
        if op == "eq":
            return col == value
        if op == "ne":
            return col != value
        raise HTTPException(400, f"文本字段不支持操作符：{op}")
    # number / date
    if op == "eq":
        return col == value
    if op == "ne":
        return col != value
    if op == "between":
        lo, hi = split_range(value)
        if lo in (None, "") or hi in (None, ""):
            raise HTTPException(400, "区间筛选需要填写完整的起止值")
        if ftype == "number":
            return and_(col >= to_float(lo), col <= to_float(hi))
        # 日期字符串比较：排除空值
        return and_(col.is_not(None), col != "", col >= lo, col <= hi)
    if ftype == "number":
        v = to_float(value) if not isinstance(value, (int, float)) else float(value)
        if op == "gt":
            return col > v
        if op == "gte":
            return col >= v
        if op == "lt":
            return col < v
        if op == "lte":
            return col <= v
        raise HTTPException(400, f"数字字段不支持操作符：{op}")
    # 日期字符串（YYYY-MM-DD 字典序即时间序）：上界比较需排除空值，下界比较天然排除空串
    if op in ("lt", "lte"):
        cond = col < value if op == "lt" else col <= value
        return and_(col.is_not(None), col != "", cond)
    if op == "gt":
        return col > value
    if op == "gte":
        return col >= value
    raise HTTPException(400, f"字段不支持操作符：{op}")


def _fold_legacy_rules(rules) -> dict:
    """历史扁平格式 → 等价嵌套树：逐条左结合折叠（`a AND b OR c` ≡ `(a AND b) OR c`）。"""
    node: dict | None = None
    for rule in rules if isinstance(rules, list) else []:
        if not isinstance(rule, dict):
            continue
        leaf = {
            "kind": "rule",
            "field": rule.get("field"),
            "op": rule.get("op"),
            "value": rule.get("value"),
            "not": rule.get("not"),
        }
        if node is None:
            node = leaf
            continue
        logic = "or" if str(rule.get("connector") or "").lower() == "or" else "and"
        if node.get("kind") == "group" and node["logic"] == logic and not node["not"]:
            node["children"].append(leaf)          # 同逻辑同层级继续平铺，避免无谓加深
        else:
            node = {"kind": "group", "logic": logic, "not": False, "children": [node, leaf]}
    if node is None:
        return {"kind": "group", "logic": "and", "not": False, "children": []}
    if node.get("kind") == "group":
        return node
    return {"kind": "group", "logic": "and", "not": False, "children": [node]}


def _normalize_rule(rule: dict) -> dict:
    """规范化单条规则：字段非空、操作符必须在白名单内（字段白名单由 leaf 构造器把关）。"""
    field = str(rule.get("field") or "")
    if not field:
        raise HTTPException(400, "筛选条件缺少 field")
    op = str(rule.get("op") or "")
    if op not in ALLOWED_FILTER_OPS:
        raise HTTPException(400, f"不支持的操作符：{op}")
    return {
        "kind": "rule", "field": field, "op": op,
        "value": rule.get("value"), "not": bool(rule.get("not")),
    }


def _normalize_group(node: dict, depth: int) -> dict:
    """递归规范化分组节点：校验 logic 白名单与嵌套深度，非法子项按历史口径跳过。"""
    if depth > MAX_FILTER_DEPTH:
        raise HTTPException(400, f"筛选分组嵌套过深（最多 {MAX_FILTER_DEPTH} 层）")
    logic = str(node.get("logic") or "and").lower()
    if logic not in GROUP_LOGICS:
        raise HTTPException(400, f"分组逻辑运算符非法：{node.get('logic')}")
    children = node.get("children")
    if children is None:
        children = []
    if not isinstance(children, list):
        raise HTTPException(400, "筛选分组 children 需为数组")
    group = {"kind": "group", "logic": logic, "not": bool(node.get("not")), "children": []}
    for child in children:
        if not isinstance(child, dict):
            continue
        is_group = child.get("kind") == "group" or isinstance(child.get("children"), list)
        group["children"].append(_normalize_group(child, depth + 1) if is_group else _normalize_rule(child))
    return group


def parse_filter_tree(filters: str) -> dict | None:
    """解析聚合筛选 JSON 为规范化条件树；空值/无有效条件返回 None，结构非法直接 400。"""
    if not filters:
        return None
    try:
        payload = json.loads(filters)
    except (ValueError, TypeError):
        raise HTTPException(400, "filters 参数格式错误，需为 JSON 字符串")
    if isinstance(payload, list):
        payload = {"rules": payload}
    if not isinstance(payload, dict):
        raise HTTPException(400, "filters 参数结构非法，需为条件对象或规则数组")
    if "children" not in payload and "rules" in payload:
        payload = _fold_legacy_rules(payload.get("rules"))
    tree = _normalize_group(payload, depth=1)
    rules = count_filter_rules(tree)
    if rules == 0:                      # 仅有空分组也算「无有效条件」
        return None
    if rules > MAX_FILTER_RULES:
        raise HTTPException(400, f"筛选条件过多（最多 {MAX_FILTER_RULES} 条）")
    return tree


def count_filter_rules(node: dict) -> int:
    """条件树中的规则条数（分组只作层级容器，不计入）。"""
    if node.get("kind") != "group":
        return 1
    return sum(count_filter_rules(child) for child in node.get("children") or [])


def build_tree_condition(node: dict, leaf_builder) -> object | None:
    """条件树 → SQLAlchemy 表达式；空分组（无有效子条件）自动忽略，整体为空返回 None。

    leaf_builder(field, op, value) 由调用方提供（负责字段白名单与派生/关联字段特化），
    返回**未取反**的单条规则表达式；取反（`not`）一律由本函数在节点层统一施加。
    """
    if node.get("kind") != "group":
        expr = leaf_builder(node.get("field", ""), node.get("op", ""), node.get("value"))
        return ~expr if node.get("not") else expr
    parts = []
    for child in node.get("children") or []:
        cond = build_tree_condition(child, leaf_builder)
        if cond is not None:
            parts.append(cond)
    if not parts:
        return None
    expr = parts[0]
    for cond in parts[1:]:
        expr = (expr | cond) if node.get("logic") == "or" else (expr & cond)
    return ~expr if node.get("not") else expr
