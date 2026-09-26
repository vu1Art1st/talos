"""出站目标（SSRF）守卫测试（安全审计 TALOS-2026-003/004 修复回归）。

覆盖：
- `assert_public_url` 对内网/回环/链路本地/共享地址/非 http(s)/无主机的拒绝，公网 IP 与白名单放行；
- 通知渠道写入侧（schema）拒绝内网 webhook；
- 通知任务发送前兜底校验：目标被拒时**不发起任何出站请求**；放行时禁用重定向跟随；
- 报告导出侧：远程图片不再进入 htmldocx 抓取路径（回归见 test_report_builder.py）。
"""
import httpx
import pytest

from app.core.config import settings
from app.core.outbound import assert_public_url
from app.services import notify_service


# ---------- 目标判定 ----------
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/hook",                 # 回环
    "http://localhost/hook",                 # 域名解析到回环
    "http://10.0.0.5/hook",                  # RFC1918
    "http://172.16.5.5/hook",
    "http://172.31.255.254/hook",
    "http://192.168.1.1/hook",
    "http://169.254.169.254/latest/meta-data/",   # 云元数据
    "http://100.64.0.1/hook",                # CGNAT
    "http://0.0.0.0/hook",
    "http://[::1]/hook",                     # IPv6 回环
    "http://[fd00::1]/hook",                 # IPv6 ULA
    "ftp://example.com/hook",                # 协议不允许
    "file:///etc/passwd",
    "http:///no-host",
    "",
])
def test_assert_public_url_blocks(url):
    with pytest.raises(ValueError):
        assert_public_url(url, field="webhook 地址")


def test_assert_public_url_allows_public_ip():
    assert assert_public_url("https://1.1.1.1/hook") == "https://1.1.1.1/hook"
    assert assert_public_url("http://[2606:4700:4700::1111]/hook").endswith("/hook")


def test_assert_public_url_allowlist_bypass(monkeypatch):
    monkeypatch.setattr(settings, "NOTIFY_HOST_ALLOWLIST", "notify.corp.local, other.local")
    # 白名单主机跳过 IP 判定（企业自建内网中继场景）
    assert assert_public_url("http://notify.corp.local/hook") == "http://notify.corp.local/hook"


# ---------- 写入侧：通知渠道 ----------
async def test_notify_channel_rejects_internal_webhook(client, auth):
    resp = await client.post(
        "/api/v1/notify-channels",
        headers=auth,
        json={
            "name": "ssrf-probe", "type": "wecom",
            "config": {"url": "http://169.254.169.254/latest/meta-data/"},
            "events": ["vuln_created"], "is_active": True,
        },
    )
    assert resp.status_code == 422, resp.text
    assert "内网" in resp.json()["detail"]


# ---------- 发送侧：兜底校验与请求参数（P1-3 起发送逻辑收敛到 notify_service.perform_send） ----------
async def test_perform_send_blocks_internal_target(monkeypatch):
    """存量渠道配置或 DNS 事后变化时，发送前兜底校验必须拦住，且不得发起任何请求。"""
    def _boom(*args, **kwargs):
        raise AssertionError("目标被拒时不应构造出站客户端")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    for channel_type, url in (
        ("wecom", "http://127.0.0.1:8099/hook"),
        ("dingtalk", "http://10.1.2.3/hook"),
    ):
        status_code, error = await notify_service.perform_send(
            channel_type, {"url": url}, "标题", "正文",
        )
        assert status_code == 0
        assert "SSRF" in error or "拒绝" in error
        # 不可重试（配置错误，重试无意义）
        assert not notify_service.error_is_retryable(error)


async def test_perform_send_public_target_without_redirect(monkeypatch):
    captured: dict = {}

    class _Resp:
        status_code = 200

    class _Client:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def post(self, url, json=None):
            captured["url"] = url
            captured["payload"] = json
            return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    status_code, error = await notify_service.perform_send(
        "wecom", {"url": "https://1.1.1.1/hook"}, "标题", "正文",
    )

    assert (status_code, error) == (200, "")
    assert captured["url"] == "https://1.1.1.1/hook"
    # 不跟随重定向：重定向目标同样可能指向内网
    assert captured["follow_redirects"] is False
    assert captured["payload"]["msgtype"] == "markdown"


async def test_perform_send_error_is_sanitized(monkeypatch):
    """错误信息脱敏：不得回显 webhook 地址中的密钥（P1-3 验收）。"""
    secret_url = "https://1.1.1.1/hook?key=TOPSECRET"

    def _boom(*args, **kwargs):
        raise httpx.ConnectError(f"failed to connect to {secret_url}")

    monkeypatch.setattr(httpx, "AsyncClient", _boom)
    _status, error = await notify_service.perform_send(
        "wecom", {"url": secret_url}, "标题", "正文",
    )
    assert "TOPSECRET" not in error
    assert notify_service.error_is_retryable(error)  # 网络错误可重试
