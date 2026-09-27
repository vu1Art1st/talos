"""P2-1 / P2-4 纯逻辑守卫：数据范围条件可编译，且不会把未知范围回退为全量。"""
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api.v1.search import _plain_text
from app.core.data_scope import DataScope, _scope_condition
from app.models import Asset, Report, SpringAction, Vul


def _compile(model, scope: DataScope) -> str:
    stmt = select(model).where(_scope_condition(scope, model))
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_department_scope_compiles_business_conditions():
    scope = DataScope(
        user_id=7,
        mode="department",
        group_ids=(1, 2),
        group_names=("研发部", "运维部"),
        group_user_ids=(7, 8, 9),
    )
    for model in (Asset, Vul, Report, SpringAction):
        sql = _compile(model, scope)
        assert "SELECT" in sql
        assert "WHERE" in sql


def test_unknown_scope_is_fail_closed():
    scope = DataScope(user_id=7, mode="unknown")
    assert "false" in _compile(Asset, scope).lower()


def test_all_scope_does_not_add_restriction():
    scope = DataScope(user_id=7, mode="all")
    assert str(_scope_condition(scope, Asset)) == "true"


def test_search_snippet_strips_html_and_collapses_space():
    assert _plain_text("<p>SQL&nbsp;注入</p>\n 测试") == "SQL 注入 测试"
