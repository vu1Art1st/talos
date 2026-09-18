"""开发种子脚本的目标库守卫回归测试（2026-09-17 审计 A-4）。

`scripts/seed_dev_data.py` 会逐表 DELETE 全部业务表，而它此前只用
`os.environ.setdefault("VP_DATABASE_URL", "sqlite+aiosqlite:///./dev.db")` 注入默认 DSN：
若环境中已导出指向测试/生产库的 `VP_DATABASE_URL`，脚本会直接清空该库。
现增加显式守卫：目标不是本地 SQLite dev.db 即拒绝执行。

注意：本模块**在导入期**（环境变量仍为 conftest 注入的测试库）完成 `scripts.seed_dev_data`
导入，之后只在测试内改环境变量后调用守卫函数。否则会在 monkeypatch 期间首次导入
`app.core.config`（模块级单例），把进程级 DSN 污染成测试用例里的假 DSN。
"""
import pytest

import scripts.seed_dev_data as seed_dev_data  # noqa: E402  必须在 monkeypatch 之前导入


def test_seed_refuses_non_sqlite_target(monkeypatch):
    monkeypatch.setenv("VP_DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/vulnplatform")

    with pytest.raises(SystemExit) as exc:
        seed_dev_data._assert_dev_database()
    assert exc.value.code == 2


def test_seed_refuses_other_sqlite_file(monkeypatch):
    monkeypatch.setenv("VP_DATABASE_URL", "sqlite+aiosqlite:///./prod.db")

    with pytest.raises(SystemExit):
        seed_dev_data._assert_dev_database()


def test_seed_accepts_dev_sqlite(monkeypatch):
    monkeypatch.setenv("VP_DATABASE_URL", "sqlite+aiosqlite:///./dev.db")

    seed_dev_data._assert_dev_database()  # 不抛异常即通过
