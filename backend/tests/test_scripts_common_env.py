"""维护脚本本地环境补齐（根 .env + 开发库 DSN 派生）测试。"""
import os

from scripts._common import ensure_local_env


def test_ensure_local_env_loads_env_and_derives_dsn(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_USER=user\nPOSTGRES_PASSWORD=p@ss\nPOSTGRES_DB=vulnplatform\n"
        "VP_SECRET_KEY=0123456789abcdef0123456789abcdef\n",
        encoding="utf-8",
    )
    for key in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "VP_SECRET_KEY", "VP_DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)

    ensure_local_env(env_file)

    assert os.environ["VP_SECRET_KEY"] == "0123456789abcdef0123456789abcdef"
    assert os.environ["VP_DATABASE_URL"] == (
        "postgresql+asyncpg://user:p%40ss@127.0.0.1:5432/vulnplatform"
    )


def test_ensure_local_env_does_not_override_explicit_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_PASSWORD=from-file\n", encoding="utf-8")
    monkeypatch.setenv("VP_DATABASE_URL", "postgresql+asyncpg://explicit/db")
    monkeypatch.setenv("POSTGRES_PASSWORD", "explicit")

    ensure_local_env(env_file)

    assert os.environ["POSTGRES_PASSWORD"] == "explicit"
    assert os.environ["VP_DATABASE_URL"] == "postgresql+asyncpg://explicit/db"
