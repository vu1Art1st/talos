"""清理测试残留 schema（`test_*` / `mig_*`）。

背景：测试不再共用 `public`，而是**每个 pytest 进程独占一个 schema**（`conftest._run_schema`，
见 docs/LOCAL_DEV_SETUP.md 第四节）。这样并发跑测试互不干扰，代价是：进程被强杀（CI 取消、
kill -9 等）时可能留下未清理的 schema。本脚本用于回收它们。

安全设计：
- 只操作 `test_*` / `mig_*` schema，绝不动 `public` 与业务 schema；
- **默认只列出不删除**，必须显式加 `--yes` 才执行删除（正在并发运行的测试的 schema 也在列表里，
  所以「确认无人并发」这一步必须由人来拍板）；
- 目标库必须是回环地址上的 `*_test` 库（与 `seed_dev_data.py` 的守卫同口径，fail-closed）；
- **不依赖 app 配置**（自己解析 DSN），因此无需 VP_SECRET_KEY 即可运行——它是纯运维工具。

用法（backend 目录）：

    python -m scripts.prune_test_schemas            # 只列出残留
    python -m scripts.prune_test_schemas --yes      # 删除（确认无并发测试在跑）
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from scripts._common import run  # noqa: E402

# 本工具负责的残留 schema 模式（与 conftest / test_migrations 的命名口径一致）
_LIKE_PATTERNS = ("test\\_%", "mig\\_%")
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


def _resolve_dsn() -> str:
    """VP_DATABASE_URL 优先；否则从仓库根 .env 的 POSTGRES_* 凭据派生测试库 DSN（与 conftest 同口径）。"""
    dsn = os.environ.get("VP_DATABASE_URL", "").strip()
    if dsn:
        return dsn
    creds: dict[str, str] = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*(POSTGRES_USER|POSTGRES_PASSWORD|POSTGRES_DB)\s*=\s*(.+?)\s*$", line)
            if m:
                creds[m.group(1)] = m.group(2)
    user = creds.get("POSTGRES_USER", "vulnplatform")
    password = creds.get("POSTGRES_PASSWORD")
    if not password:
        raise SystemExit(
            "无法确定测试库连接：未设置 VP_DATABASE_URL，且仓库根目录 .env 缺少 POSTGRES_PASSWORD"
            "（见 docs/LOCAL_DEV_SETUP.md）"
        )
    return f"postgresql+asyncpg://{user}:{password}@127.0.0.1:5432/vulnplatform_test"


def _assert_test_database(dsn: str) -> None:
    """fail-closed 守卫：只允许清理回环地址上的 `*_test` 库。"""
    m = re.search(r"@([^/:]+)(?::\d+)?/([^/?]+)", dsn)
    host, dbname = (m.group(1), m.group(2)) if m else ("", "")
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit(f"拒绝执行：目标数据库主机不是回环地址（host={host or '<未知>'}）")
    if not re.search(r"_test(_[a-z0-9]+)?$", dbname):
        raise SystemExit(
            f"拒绝执行：目标库名不是测试库（dbname={dbname or '<未知>'}）；本脚本只允许清理 *_test 库"
        )


async def main(confirm: bool = False) -> None:
    dsn = _resolve_dsn()
    _assert_test_database(dsn)
    engine = create_async_engine(dsn, pool_pre_ping=True)

    where = " OR ".join(f"schema_name LIKE '{p}'" for p in _LIKE_PATTERNS)
    try:
        async with engine.begin() as conn:
            names = (await conn.execute(
                text(f"SELECT schema_name FROM information_schema.schemata WHERE {where} ORDER BY schema_name")
            )).scalars().all()

        if not names:
            print("没有残留的 test_*/mig_* schema")
            return

        print(f"发现 {len(names)} 个残留 schema：{', '.join(names)}")
        if not confirm:
            print("未删除（默认只列出）。确认当前没有并发测试在运行后，加 --yes 执行删除。")
            return

        async with engine.begin() as conn:
            for name in names:
                await conn.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
        print(f"已删除 {len(names)} 个 schema")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    run(main, confirm="--yes" in sys.argv)
