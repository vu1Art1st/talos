import os
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_DB_FILE = _TESTS_DIR / "test_vp.db"

# 必须在导入 app 之前设置环境变量（settings 为模块级单例）
os.environ["VP_DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}"
os.environ["VP_DISABLE_QUEUE"] = "1"
os.environ["VP_STORAGE_DIR"] = str(_TESTS_DIR / "test_storage")
# 使用 >=32 字符的密钥以通过生产校验；固定内置 admin 初始口令供登录夹具使用
os.environ["VP_SECRET_KEY"] = "test-secret-key-0123456789abcdef-0123456789"
os.environ["VP_INITIAL_ADMIN_PASSWORD"] = "admin123"

if _DB_FILE.exists():
    _DB_FILE.unlink()

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client():
    from app.main import app

    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


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
