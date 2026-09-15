"""`app/main.py` 全局异常处理器：统一 4xx / 5xx 的 JSON 响应体。

前端按响应状态码跳转自定义错误页（`frontend/src/utils/errorPage.ts`），
故这里只需保证「状态码正确 + 文案可读 + 不泄露内部细节」。
"""

import json

from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request


def _make_request(path: str = "/api/v1/boom") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("test", 80),
            "client": ("test", 1234),
            "root_path": "",
        }
    )


async def test_unhandled_exception_returns_json_500():
    from app.main import app

    handler = app.exception_handlers[Exception]
    resp = await handler(_make_request(), RuntimeError("boom-must-not-leak"))

    assert resp.status_code == 500
    assert json.loads(resp.body) == {"detail": "服务器内部错误，请稍后重试"}
    assert "boom-must-not-leak" not in resp.body.decode()


async def test_unhandled_exception_end_to_end_returns_json_500():
    """走真实请求路径：临时挂一条必抛异常的路由，验证处理器确实被接入。"""
    from app.main import app

    marker = "/api/v1/_test_boom"

    async def _boom():
        raise RuntimeError("boom-must-not-leak")

    app.add_api_route(marker, _boom, methods=["GET"])
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(marker)
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != marker]

    assert resp.status_code == 500
    assert resp.json() == {"detail": "服务器内部错误，请稍后重试"}


async def test_validation_error_returns_json_422():
    from app.main import app

    handler = app.exception_handlers[RequestValidationError]
    resp = await handler(_make_request(), RequestValidationError([]))

    assert resp.status_code == 422
    assert json.loads(resp.body) == {"detail": "请求参数校验失败，请检查填写内容"}
