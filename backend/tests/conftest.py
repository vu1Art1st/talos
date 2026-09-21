import os
import re
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
# 护栏：测试 fixture 会整库清空 schema，目标库必须以 _test 结尾，防止误连开发库/生产库
_m = re.search(r"/([^/?]+)(?:\?[^/]*)?$", _TEST_DSN)
if not _m or not _m.group(1).endswith("_test"):
    pytest.fail(
        f"测试目标库必须以 _test 结尾（当前 DSN 库名：{_m.group(1) if _m else '<未知>'}）。\n"
        "conftest 的 session fixture 会整库 DROP SCHEMA，非 *_test 库一律拒绝连接。"
    )

os.environ["VP_DATABASE_URL"] = _TEST_DSN
os.environ["VP_DISABLE_QUEUE"] = "1"
# 测试不依赖外部 Redis：限流/锁定计数直接走进程内内存（等价于「Redis 不可用」的降级路径）。
# 否则每次调用都要付连接超时（G7 保证有界，但仍会显著拖慢全量测试）
os.environ["VP_DISABLE_REDIS"] = "1"
os.environ["VP_STORAGE_DIR"] = str(_TESTS_DIR / "test_storage")
# 使用 >=32 字符的密钥以通过生产校验；固定内置 admin 初始口令供登录夹具使用
os.environ["VP_SECRET_KEY"] = "test-secret-key-0123456789abcdef-0123456789"
os.environ["VP_INITIAL_ADMIN_PASSWORD"] = "admin123"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402


async def _reset_schema() -> None:
    """清空并重建 public schema（session 开始前与结束后各执行一次）。"""
    from app.db import engine

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))


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
    # session 结束：释放连接池后清空 schema，保持测试库干净
    await engine.dispose()
    await _reset_schema()
    import shutil

    shutil.rmtree(_TESTS_DIR / "test_storage", ignore_errors=True)


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
