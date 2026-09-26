"""API 集成测试：健康检查探针（ROADMAP P0-3）。

口径：数据库为必需依赖；队列启用时 Redis 与 worker 心跳同为必需；Gotenberg 为可选能力
（不可用不影响就绪）。探针响应不得包含敏感信息（DSN / 密码 / 内网地址）。
"""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")


class _FakePool:
    """最小 arq 连接池替身：只实现 ready 探针用到的 ping / get。"""

    def __init__(self, worker_alive: bool):
        self.worker_alive = worker_alive

    async def ping(self):
        return True

    async def get(self, key):
        return b"j_complete=0" if self.worker_alive else None


class _BrokenPool:
    async def ping(self):
        raise ConnectionError("connection refused to 10.0.0.1:6379")

    async def get(self, key):
        raise ConnectionError("connection refused")


@pytest.fixture
def fast_gotenberg(monkeypatch):
    """把 Gotenberg 指向必然拒绝连接的端口：探测快速失败，且不影响就绪判定。"""
    from app.core.config import settings

    monkeypatch.setattr(settings, "GOTENBERG_URL", "http://127.0.0.1:1")


async def test_health_probes_and_request_id(client: AsyncClient, fast_gotenberg):
    """兼容探针恒 200；live 不查依赖；ready 返回逐项状态且响应头带 request_id。"""
    resp = await client.get("/api/health")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}
    assert resp.headers.get("X-Request-Id")

    resp = await client.get("/api/health/live")
    assert resp.status_code == 200 and resp.json()["status"] == "alive"

    resp = await client.get("/api/health/ready")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"]["ok"] is True
    # 测试环境 VP_DISABLE_QUEUE=1 → Redis / worker 不参与就绪判定
    assert body["checks"]["redis"]["required"] is False
    assert body["checks"]["worker"]["required"] is False
    # Gotenberg 为可选依赖：不可用也不得让实例 unready
    assert body["checks"]["gotenberg"]["required"] is False

    # 传入的 request_id 被复用（便于前端 / 网关串联日志）
    resp = await client.get("/api/health/live", headers={"X-Request-Id": "trace-abc"})
    assert resp.headers.get("X-Request-Id") == "trace-abc"


async def test_ready_fails_when_database_down(client: AsyncClient, monkeypatch, fast_gotenberg):
    """必需依赖（数据库）不可用 → 503，且不泄露内部错误细节。"""
    import app.db as db_module

    class _Boom:
        def __call__(self):
            raise ConnectionError("could not connect to postgresql://user:pw@10.1.2.3/db")

    monkeypatch.setattr(db_module, "async_session_maker", _Boom())
    resp = await client.get("/api/health/ready")
    assert resp.status_code == 503, resp.text
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"]["ok"] is False
    assert body["checks"]["database"]["required"] is True
    # 敏感信息（DSN / 凭据 / 内网地址）不得出现在探针响应里
    assert "postgresql://" not in resp.text and "pw@" not in resp.text
    assert "10.1.2.3" not in resp.text


async def test_ready_reflects_queue_dependencies(client: AsyncClient, monkeypatch, fast_gotenberg):
    """故障注入：队列启用时 Redis 断连 / 无 worker 心跳 / 全部正常三种状态。"""
    from app.core.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "DISABLE_QUEUE", False)

    # 1) 未建立队列连接（启动时 Redis 不可用，已降级为进程内执行）
    monkeypatch.setattr(app.state, "arq", None, raising=False)
    resp = await client.get("/api/health/ready")
    assert resp.status_code == 503, resp.text
    assert resp.json()["checks"]["redis"]["ok"] is False
    assert resp.json()["checks"]["worker"]["ok"] is False

    # 2) Redis 不可用
    monkeypatch.setattr(app.state, "arq", _BrokenPool(), raising=False)
    resp = await client.get("/api/health/ready")
    assert resp.status_code == 503, resp.text
    assert resp.json()["checks"]["redis"]["ok"] is False
    assert "10.0.0.1" not in resp.text  # 不泄露内网地址

    # 3) Redis 正常但无 worker 心跳
    monkeypatch.setattr(app.state, "arq", _FakePool(worker_alive=False), raising=False)
    resp = await client.get("/api/health/ready")
    assert resp.status_code == 503, resp.text
    assert resp.json()["checks"]["redis"]["ok"] is True
    assert resp.json()["checks"]["worker"]["ok"] is False

    # 4) 依赖齐备 → 就绪
    monkeypatch.setattr(app.state, "arq", _FakePool(worker_alive=True), raising=False)
    resp = await client.get("/api/health/ready")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ready"
