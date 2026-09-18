"""客户端信息统一解析：真实来源 IP / User-Agent。

背景：生产环境请求链路为 浏览器 → Nginx(frontend 容器) → API 容器，
直接读 ``request.client.host`` 拿到的是 Nginx 容器内网 IP（如 172.18.x.x），
必须基于代理透传的头还原真实客户端 IP。因此所有需要「来源 IP / UA」的调用
（审计日志、登录防爆破、锁定判定等）一律走本模块，禁止散落直接读 ``request.client.host``。

取值口径（2026-09-19 安全整改 批次 E-4）：由 ``VP_TRUSTED_PROXY_HOPS`` 显式声明本服务
前方**可信代理层数** N，客户端 IP 取 ``X-Forwarded-For`` 右起第 N 项：

- N = 1（默认，对应「浏览器 → 前端 Nginx → API」）：取链尾，即 Nginx 追加的 ``$remote_addr``；
- N = 0：完全不信任转发头，仅用 socket 对端地址（API 直接对外暴露的形态）；
- 外层还有一层（如宿主 Nginx / CDN）时把 N 调成 2，依此类推；
- XFF 项数不足 N（被上层裁剪）或选中项不是合法 IP → 退回 ``X-Real-IP``，再退回 socket 对端。

为什么不再用「右起第一个非内网地址」的启发式（旧实现）：该启发式在客户端伪造公网 XFF 时
会采信伪造值——实测带 ``X-Forwarded-For: 1.2.3.4`` 的请求会让审计日志记录 1.2.3.4。新口径下
最右第 N 项恒为可信代理写入的地址，客户端无法伪造；内网办公场景也不再依赖保留地址特判。

安全前提：每一层可信代理都必须用 ``proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;``
追加真实对端；API 端口禁止直接对外暴露（否则 hops 配置失去意义）。
"""
import ipaddress

from fastapi import Request

from app.core.config import settings


def _clean_entry(entry: str) -> str:
    """清洗单个 IP 条目：去首尾空白、剥离端口（IPv4 与 [v6]:port 形式）。"""
    entry = entry.strip()
    if not entry:
        return ""
    if entry.startswith("["):  # [::1]:8080
        if "]" in entry:
            entry = entry[1:entry.index("]")]
    elif entry.count(":") == 1 and entry.rsplit(":", 1)[1].isdigit():
        entry = entry.rsplit(":", 1)[0]  # 1.2.3.4:5678
    return entry


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def get_client_ip(request: Request) -> str:
    """取真实客户端 IP（口径见模块 docstring）。"""
    peer = _clean_entry(request.client.host) if request.client else ""
    hops = max(0, settings.TRUSTED_PROXY_HOPS)
    if hops == 0:
        return peer[:64]

    xff = request.headers.get("x-forwarded-for", "")
    entries = [e for e in (_clean_entry(x) for x in xff.split(",")) if e]
    if len(entries) >= hops and _is_ip(entries[-hops]):
        return entries[-hops][:64]

    x_real = _clean_entry(request.headers.get("x-real-ip", ""))
    if x_real and _is_ip(x_real):
        return x_real[:64]
    return peer[:64]


def get_user_agent(request: Request) -> str:
    """取 User-Agent：剔除控制字符并截断到 256 字符。"""
    ua = request.headers.get("user-agent", "")
    if not ua:
        return ""
    ua = "".join(ch for ch in ua if ch.isprintable())
    return ua[:256]
