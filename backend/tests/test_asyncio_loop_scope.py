"""事件循环作用域守卫（2026-09-21 由 SQLite→PostgreSQL 迁移暴露）。

背景：asyncpg 的连接对象严格绑定创建它的 event loop。conftest 的 client/token/auth
均为 session 级 fixture，连接池建立在 session loop 上；若测试默认回落到函数级 loop，
就会跨 loop 复用连接，抛 `Event loop is closed` / `'NoneType' object has no attribute
'send'`。SQLite/aiosqlite 走独立线程、对 loop 归属不敏感，故该缺陷被长期掩盖（迁移时
一次性暴露为 24 failed / 1 error）。

本文件从两个层面守卫：
1. 静态：pytest.ini 的两条 loop 作用域配置必须都在且为 session；
2. 运行时：测试实际运行的 loop 必须与 session 级 fixture 所在的 loop 为同一个。
"""

import asyncio

import pytest
import pytest_asyncio


def test_pytest_ini_declares_session_loop_scope(pytestconfig):
    """pytest.ini 必须同时声明 fixture 与测试两侧的 session 作用域。

    只设 fixture 一侧（历史配置）正是本次 24 例失败的成因：fixture 在 session loop
    建池，测试却在函数级 loop 里用池。
    """
    assert pytestconfig.getini("asyncio_default_fixture_loop_scope") == "session", (
        "pytest.ini 缺少 asyncio_default_fixture_loop_scope = session"
    )
    assert pytestconfig.getini("asyncio_default_test_loop_scope") == "session", (
        "pytest.ini 缺少 asyncio_default_test_loop_scope = session——"
        "测试会回落为函数级 loop，与 session 级连接池错配（asyncpg 跨 loop 报错）"
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def _session_loop_id() -> int:
    """记录 session loop 的身份，供用例比对。"""
    return id(asyncio.get_running_loop())


async def test_tests_share_the_session_event_loop(client, _session_loop_id):
    """用例运行时的 loop 必须就是 session fixture 所在的 loop。

    若作用域配置被改坏，本用例的 loop 与 fixture 的 loop 不同 → 断言失败，
    且随后的连接池释放会伴随 `Event loop is closed` 噪音，报错指向明确。
    """
    assert id(asyncio.get_running_loop()) == _session_loop_id, (
        "测试运行在函数级 loop 上，与 session 级 fixture 的 loop 不同——"
        "请检查 pytest.ini 的 asyncio_default_test_loop_scope = session 是否被移除"
    )


async def test_engine_pool_is_usable_from_test_loop(client, auth):
    """池内连接可从测试侧正常使用（跨 loop 复用时会在此暴露）。"""
    resp = await client.get("/api/v1/auth/me", headers=auth)
    assert resp.status_code == 200, resp.text


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
