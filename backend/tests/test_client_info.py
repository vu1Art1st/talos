"""客户端信息解析测试：真实 IP / User-Agent 的取址逻辑。

2026-09-19（批次 E-4）改为**显式可信代理层数**口径 `VP_TRUSTED_PROXY_HOPS`：
客户端 IP = X-Forwarded-For 右起第 N 项（N=层数）；链条不足或非法 → X-Real-IP → socket 对端。
旧口径（右起第一个非内网地址）在客户端伪造公网 XFF 时会被采信，故被替换。
"""
import pytest
from fastapi import Request

from app.core.client_info import get_client_ip, get_user_agent
from app.core.config import settings


def _make_request(headers: dict[str, str] | None = None, client_host: str = "172.18.0.5") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/health",
        "raw_path": b"/api/v1/health",
        "headers": [
            (k.lower().encode(), v.encode())
            for k, v in (headers or {}).items()
        ],
        "query_string": b"",
        "client": (client_host, 54321),
        "server": ("test", 80),
        "scheme": "http",
    }
    return Request(scope)


def test_no_proxy_headers_falls_back_to_client_host():
    request = _make_request(client_host="203.0.113.10")
    assert get_client_ip(request) == "203.0.113.10"


def test_single_hop_takes_last_entry():
    # 默认 hops=1（浏览器 → 前端 Nginx → API）：取链尾，即 Nginx 追加的 $remote_addr
    request = _make_request({"X-Forwarded-For": "203.0.113.10, 172.18.0.5"})
    assert get_client_ip(request) == "172.18.0.5"


def test_two_hops_takes_second_from_right(monkeypatch):
    # 宿主 Nginx → docker Nginx：链尾是内层代理看到的对端，客户端在右起第 2 项
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    request = _make_request({"X-Forwarded-For": "203.0.113.10, 127.0.0.1, 172.18.0.5"})
    assert get_client_ip(request) == "127.0.0.1"


def test_three_hops_reaches_client(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 3)
    request = _make_request({"X-Forwarded-For": "203.0.113.10, 127.0.0.1, 172.18.0.5"})
    assert get_client_ip(request) == "203.0.113.10"


def test_spoofed_public_prefix_is_ignored():
    # 回归（批次 E-4）：客户端伪造公网地址时，链尾（可信代理写入）优先，伪造值不得被采信
    request = _make_request({"X-Forwarded-For": "1.2.3.4, 203.0.113.10"})
    assert get_client_ip(request) == "203.0.113.10"
    request = _make_request({"X-Forwarded-For": "10.0.0.66, 203.0.113.10"})
    assert get_client_ip(request) == "203.0.113.10"


def test_hops_zero_ignores_forward_headers(monkeypatch):
    # 完全不信任转发头（API 直接暴露的形态）：只认 socket 对端
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)
    request = _make_request({"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}, client_host="192.0.2.7")
    assert get_client_ip(request) == "192.0.2.7"


def test_internal_chain_last_entry_kept():
    # 内网办公场景：链尾为保留地址也照常返回（不再做「跳过内网」特判）
    request = _make_request({"X-Forwarded-For": "10.0.0.10, 192.168.1.50"})
    assert get_client_ip(request) == "192.168.1.50"


def test_xff_entry_with_port_stripped(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    request = _make_request({"X-Forwarded-For": "203.0.113.10:8080, 172.18.0.5"})
    assert get_client_ip(request) == "203.0.113.10"


def test_xff_ipv6_with_port_stripped(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    request = _make_request({"X-Forwarded-For": "[2606:4700:4700::1111]:8080, 172.18.0.5"})
    assert get_client_ip(request) == "2606:4700:4700::1111"


def test_x_real_ip_fallback_when_chain_too_short(monkeypatch):
    # XFF 项数不足 hops（上层裁剪）→ 退回 X-Real-IP
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    request = _make_request({"X-Forwarded-For": "172.18.0.5", "X-Real-IP": "203.0.113.10"})
    assert get_client_ip(request) == "203.0.113.10"


def test_invalid_entry_falls_back_to_peer():
    # 选中项不是合法 IP（伪造非 IP 字符串）→ 退回 socket 对端，不把脏值写进审计
    request = _make_request({"X-Forwarded-For": "unknown"}, client_host="172.18.0.5")
    assert get_client_ip(request) == "172.18.0.5"


def test_prefers_xff_over_x_real_ip():
    # 两者都存在且一致时以 XFF 为准；不一致时同样取可信链尾（X-Real-IP 与链尾同源，正常应相同）
    request = _make_request({"X-Real-IP": "172.18.0.5", "X-Forwarded-For": "203.0.113.10, 172.18.0.5"})
    assert get_client_ip(request) == "172.18.0.5"


def test_empty_headers_returns_empty():
    assert get_client_ip(_make_request(headers={}, client_host="172.18.0.5")) == "172.18.0.5"


def test_user_agent_passthrough_and_trim():
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/130.0"
    assert get_user_agent(_make_request({"User-Agent": ua})) == ua


def test_user_agent_control_chars_removed():
    assert get_user_agent(_make_request({"User-Agent": "abc\x00\x1bdef"})) == "abcdef"


def test_user_agent_missing_returns_empty():
    assert get_user_agent(_make_request(headers={})) == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
