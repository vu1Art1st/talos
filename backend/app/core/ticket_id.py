"""工单ID 派生口径唯一实现（渗透测试工单与漏扫基线工单共用）。

口径：`ticket_id_manual` 优先；否则 `receive_time`(YYYY-MM-DD) + `ticket_seq` → `YYYYMMDD-N`。

维护提醒：聚合筛选与关键词搜索另有 SQL 表达式实现（`app/services/plan_query.py` 的
`_ticket_id_filter_expr` / `plan_search_condition` / `nonpen_search_condition`），
三处必须保持同口径；改动本函数时必须同步核对上述表达式。
"""


def derive_ticket_id(
    ticket_id_manual: str | None,
    receive_time: str | None,
    ticket_seq: int | None,
) -> str:
    """派生工单ID；无手动值且缺接收日期/序号时返回空串。"""
    if ticket_id_manual:
        return ticket_id_manual
    if not receive_time or not ticket_seq:
        return ""
    date_str = receive_time.replace("-", "")[:8]
    return f"{date_str}-{ticket_seq}"
