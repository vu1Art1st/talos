"""聚合筛选通用引擎：按字段类型把「规则 JSON」翻译为 SQLAlchemy 表达式。

与具体模型解耦：调用方提供列对象与字段类型（text/enum/number/date + 是否 DateTime 列），
本模块只负责操作符白名单、区间取值与表达式构造；派生/关联字段（如工单ID、多对多、计数）
由调用方自行组装后，经 build_rules_condition 组合，或独立拼入查询条件。
"""
import json

from fastapi import HTTPException
from sqlalchemy import and_, func

# 规则操作符白名单：所有接入聚合筛选的接口共用同一套语义
ALLOWED_FILTER_OPS = {
    "eq", "ne", "contains", "not_contains", "starts_with", "ends_with",
    "gt", "gte", "lt", "lte", "between", "is_empty", "is_not_empty",
}


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


def parse_filter_rules(filters: str) -> list[dict]:
    """解析聚合筛选 JSON 为规则列表（rules），格式非法直接 400，空/无规则返回空列表。"""
    if not filters:
        return []
    try:
        payload = json.loads(filters)
    except (ValueError, TypeError):
        raise HTTPException(400, "filters 参数格式错误，需为 JSON 字符串")
    rules = payload.get("rules") if isinstance(payload, dict) else None
    if not isinstance(rules, list) or not rules:
        return []
    return rules


def combine_rules(expr, cond, connector: str):
    """按规则间连接词（and/or）把新条件并入累计表达式，首条规则的 connector 忽略。"""
    if expr is None:
        return cond
    if connector == "or":
        return expr | cond
    return expr & cond
