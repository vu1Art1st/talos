import os
import re
import shutil
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent.parent
_ENV_FILE = _REPO_ROOT / ".env"


def _load_env_creds() -> dict[str, str]:
    """解析仓库根目录 .env 的 PostgreSQL 凭据（与 docker-compose / dev 脚本共用一份）。"""
    creds: dict[str, str] = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*(POSTGRES_USER|POSTGRES_PASSWORD|POSTGRES_DB)\s*=\s*(.+?)\s*$", line)
            if m:
                creds[m.group(1)] = m.group(2)
    return creds


def _build_test_dsn() -> str:
    """构造测试库 DSN：优先外部 VP_DATABASE_URL（CI services 容器），否则从根 .env 派生 vulnplatform_test。"""
    dsn = os.environ.get("VP_DATABASE_URL")
    if dsn:
        return dsn
    creds = _load_env_creds()
    user = creds.get("POSTGRES_USER", "vulnplatform")
    password = creds.get("POSTGRES_PASSWORD", "")
    if not password:
        pytest.fail(
            "无法确定测试数据库连接：未设置 VP_DATABASE_URL，且仓库根目录 .env 缺少 POSTGRES_PASSWORD。\n"
            "请按 docs/LOCAL_DEV_SETUP.md 完成 DBngin 建库，或显式导出 VP_DATABASE_URL（须指向 *_test 库）。"
        )
    return f"postgresql+asyncpg://{user}:{password}@127.0.0.1:5432/vulnplatform_test"


# 测试库 DSN（模块级确定，须在导入 app 之前设置环境变量——settings 为模块级单例）
_TEST_DSN = _build_test_dsn()
# 护栏：本 fixture 会 DROP 掉自己的 schema，目标库必须显式带 _test 标记，防止误连开发库/生产库。
# 允许分片库名（vulnplatform_test_2 / vulnplatform_test_ci），供 CI 按 job 分库时使用。
_m = re.search(r"/([^/?]+)(?:\?[^/]*)?$", _TEST_DSN)
_DB_NAME = _m.group(1) if _m else ""
if not re.search(r"_test(_[a-z0-9]+)?$", _DB_NAME):
    pytest.fail(
        f"测试目标库必须以 _test 结尾（当前 DSN 库名：{_DB_NAME or '<未知>'}）。\n"
        "conftest 的 session fixture 会 DROP 自己的 schema，非 *_test 库一律拒绝连接。"
    )


def _run_schema() -> str:
    """本次 pytest 进程独占的 schema 名。

    为什么需要：schema 由 session fixture 整段 DROP/CREATE 重建。若所有进程共用 `public`，
    两份测试同时跑就会互相清表，症状是分散在多个文件的 `relation ... does not exist`
    （2026-09-21 实测 70 failed / 219 passed 即此因），且极易被误判为代码缺陷。
    改为「每个 pytest 进程一个 schema」后互不干扰，既不需要加锁，也天然支持 pytest-xdist
    （每个 worker 是独立进程，故 worker 维度自动隔离）。

    命名：基础名取显式 VP_TEST_SCHEMA，否则 `test_<pid>`；**任何情况下都追加 xdist worker 名**
    （`_gw0`/`_gw1`…）—— 否则显式命名会让同一 job 的所有 worker 又挤回同一个 schema。
    """
    explicit = os.environ.get("VP_TEST_SCHEMA", "").strip()
    base = explicit.lower() if explicit else f"test_{os.getpid()}"
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")  # 非 xdist 时为空；xdist 下为 gw0/gw1…
    name = base + (f"_{worker}" if worker else "")
    name = re.sub(r"[^a-z0-9_]", "_", name)
    if not re.match(r"^[a-z_][a-z0-9_]*$", name):
        pytest.fail(f"非法 schema 名：{name!r}（只允许小写字母/数字/下划线，且不以数字开头）")
    return name[:63]  # PostgreSQL 标识符上限


_SCHEMA = _run_schema()

os.environ["VP_DATABASE_URL"] = _TEST_DSN
os.environ["VP_DB_SCHEMA"] = _SCHEMA
os.environ["VP_DISABLE_QUEUE"] = "1"
# 测试不依赖外部 Redis：限流/锁定计数直接走进程内内存（等价于「Redis 不可用」的降级路径）。
# 否则每次调用都要付连接超时（G7 保证有界，但仍会显著拖慢全量测试）
os.environ["VP_DISABLE_REDIS"] = "1"
# 存储目录同样按 run 隔离：并发 run 共用目录时，文件类用例会互相删掉对方的产物
_STORAGE_DIR = _TESTS_DIR / "test_storage" / _SCHEMA
os.environ["VP_STORAGE_DIR"] = str(_STORAGE_DIR)
# 使用 >=32 字符的密钥以通过生产校验；固定内置 admin 初始口令供登录夹具使用
os.environ["VP_SECRET_KEY"] = "test-secret-key-0123456789abcdef-0123456789"
os.environ["VP_INITIAL_ADMIN_PASSWORD"] = "admin123"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402


async def _drop_schema() -> None:
    """删除本 run 独占的 schema（幂等）。只动自己的 schema，不影响同库其它并发 run。"""
    from app.db import engine

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE'))


async def _reset_schema() -> None:
    """重建本 run 独占的 schema（session 开始前与结束后各执行一次）。"""
    from app.db import engine

    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{_SCHEMA}" CASCADE'))
        await conn.execute(text(f'CREATE SCHEMA "{_SCHEMA}"'))


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client():
    from app.db import engine
    from app.main import app

    try:
        await _reset_schema()
    except Exception as exc:
        pytest.fail(
            f"测试数据库连接失败：{exc}\n"
            "请确认 DBngin 的 PostgreSQL 服务已启动、vulnplatform_test 库已创建\n"
            "（建库步骤见 docs/LOCAL_DEV_SETUP.md），或显式导出 VP_DATABASE_URL 指向可用的 *_test 库。"
        )

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c
    # session 结束：释放连接池后清掉本 run 的 schema 与存储目录（保持测试库干净）
    await _drop_schema()
    await engine.dispose()
    shutil.rmtree(_STORAGE_DIR, ignore_errors=True)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def token(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "admin", "password": "admin123"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
