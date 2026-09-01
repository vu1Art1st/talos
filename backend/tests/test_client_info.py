"""客户端信息解析测试：真实 IP / User-Agent 的取址逻辑。"""
import pytest
from fastapi import Request

from app.core.client_info import get_client_ip, get_user_agent


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


def test_single_hop_xff_returns_public_ip():
    # 浏览器直连 docker Nginx：XFF 由 $proxy_add_x_forwarded_for 追加
    request = _make_request({"X-Forwarded-For": "203.0.113.10, 172.18.0.5"})
    assert get_client_ip(request) == "203.0.113.10"


def test_multi_hop_xff_skips_inner_proxy():
    # 宿主 Nginx → docker Nginx：链尾为宿主内网地址，应跳过取用户公网 IP
    request = _make_request({"X-Forwarded-For": "203.0.113.10, 127.0.0.1, 172.18.0.5"})
    assert get_client_ip(request) == "203.0.113.10"


def test_xff_with_spoofed_private_first():
    # 伪造 XFF 前缀内网地址，链尾仍是真实对端追加的公网地址
    request = _make_request({"X-Forwarded-For": "10.0.0.66, 203.0.113.10"})
    assert get_client_ip(request) == "203.0.113.10"


def test_xff_all_private_takes_last():
    # 内网办公场景：全部为保留地址时取最右（离本服务最近）一项
    request = _make_request({"X-Forwarded-For": "10.0.0.10, 192.168.1.50"})
    assert get_client_ip(request) == "192.168.1.50"


def test_xff_entry_with_port_stripped():
    request = _make_request({"X-Forwarded-For": "203.0.113.10:8080, 172.18.0.5"})
    assert get_client_ip(request) == "203.0.113.10"


def test_xff_ipv6_with_port_stripped():
    # 2606:4700::/48 为公网 IPv6（Cloudflare），链尾是 docker Nginx 追加的内网对端
    request = _make_request({"X-Forwarded-For": "[2606:4700:4700::1111]:8080, 172.18.0.5"})
    assert get_client_ip(request) == "2606:4700:4700::1111"


def test_x_real_ip_fallback():
    request = _make_request({"X-Real-IP": "203.0.113.10"})
    assert get_client_ip(request) == "203.0.113.10"


def test_prefers_xff_over_x_real_ip():
    request = _make_request({"X-Real-IP": "198.51.100.9", "X-Forwarded-For": "203.0.113.10, 172.18.0.5"})
    assert get_client_ip(request) == "203.0.113.10"


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
