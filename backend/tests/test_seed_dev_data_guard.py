"""开发种子脚本的目标库守卫回归测试（2026-09-17 审计 A-4；2026-09-21 随 SQLite 收口改造）。

`scripts/seed_dev_data.py` 会逐表 DELETE 全部业务表，因此必须显式校验目标库。守卫判据为
「PG 库名白名单（vulnplatform / vulnplatform_test）**且** 主机为回环地址」——两个条件缺一不可：
只校验库名会放过「同名远程库」，只校验主机则会放过「本机上的其它库」。

注意：本模块**在导入期**（环境变量仍为 conftest 注入的测试库）完成 `scripts.seed_dev_data`
导入，之后只在测试内改环境变量后调用守卫函数。否则会在 monkeypatch 期间首次导入
`app.core.config`（模块级单例），把进程级 DSN 污染成测试用例里的假 DSN。
"""
import pytest

import scripts.seed_dev_data as seed_dev_data  # noqa: E402  必须在 monkeypatch 之前导入


def test_seed_refuses_remote_target_with_listed_db_name(monkeypatch):
    """库名在白名单、主机非回环 → 拒绝（防同名远程/生产库被清空）。"""
    monkeypatch.setenv("VP_DATABASE_URL", "postgresql+asyncpg://vuln:pw@10.0.0.5:5432/vulnplatform")

    with pytest.raises(SystemExit) as exc:
        seed_dev_data._assert_dev_database()
    assert exc.value.code == 2


def test_seed_refuses_loopback_but_unlisted_db(monkeypatch):
    """主机为回环、库名不在白名单 → 拒绝。"""
    monkeypatch.setenv("VP_DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:5432/prod_db")

    with pytest.raises(SystemExit):
        seed_dev_data._assert_dev_database()


def test_seed_refuses_unset_dsn(monkeypatch):
    """未设置 DSN → 拒绝（不得静默回落到配置内的默认库）。"""
    monkeypatch.delenv("VP_DATABASE_URL", raising=False)

    with pytest.raises(SystemExit):
        seed_dev_data._assert_dev_database()


def test_seed_refuses_malformed_dsn(monkeypatch):
    """无法解析的 DSN → fail-closed 拒绝。"""
    monkeypatch.setenv("VP_DATABASE_URL", "not-a-dsn")

    with pytest.raises(SystemExit):
        seed_dev_data._assert_dev_database()


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql+asyncpg://u:p@127.0.0.1:5432/vulnplatform",
        "postgresql+asyncpg://u:p@localhost:5432/vulnplatform",
        "postgresql+asyncpg://u:p@127.0.0.1:5432/vulnplatform_test",
    ],
)
def test_seed_accepts_local_dev_targets(monkeypatch, dsn):
    """本机回环 + 白名单库名 → 放行。"""
    monkeypatch.setenv("VP_DATABASE_URL", dsn)

    seed_dev_data._assert_dev_database()  # 不抛异常即通过


def test_default_dsn_is_accepted_by_its_own_guard():
    """默认 DSN（解析自仓库根 .env）必须能通过本脚本自己的守卫，否则脚本默认不可用。"""
    dsn = seed_dev_data._default_dev_dsn()
    if not dsn:
        pytest.skip("仓库根 .env 缺 POSTGRES_PASSWORD，无法构造默认 DSN")

    from sqlalchemy.engine import make_url

    url = make_url(dsn)
    assert url.database in seed_dev_data._DEV_DB_NAME_WHITELIST, dsn
    assert url.host in seed_dev_data._LOOPBACK_HOSTS, dsn
