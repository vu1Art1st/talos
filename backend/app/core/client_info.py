"""客户端信息统一解析：真实来源 IP / User-Agent。

背景：生产环境请求链路为 浏览器 → Nginx(frontend 容器) → API 容器，
直接读 ``request.client.host`` 拿到的是 Nginx 容器内网 IP（如 172.18.x.x），
必须基于代理透传的 X-Forwarded-For / X-Real-IP 还原真实客户端 IP。

因此所有需要「来源 IP / UA」的调用（审计日志、登录防爆破、锁定判定等）
一律走本模块，禁止散落直接读 ``request.client.host`` / ``headers`` 的样板。
"""
import ipaddress

from fastapi import Request

# IPv4 保留/内网网段：可信代理链路中这些地址不应被当作真实客户端来源
_PRIVATE_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),     # 回环
    ipaddress.ip_network("10.0.0.0/8"),      # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),   # RFC 1918（Docker 默认网段在此区间）
    ipaddress.ip_network("192.168.0.0/16"),  # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),  # 链路本地
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT 共享地址空间
)


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


def _is_private(ip: str) -> bool:
    """判断地址是否属于回环/内网/保留段；非法地址一律视为不可信。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    if addr.version == 4:
        return any(addr in net for net in _PRIVATE_NETS)
    return addr.is_loopback or addr.is_link_local or addr.is_private


def get_client_ip(request: Request) -> str:
    """取真实客户端 IP。

    优先级：
    1. ``X-Forwarded-For``：从右往左跳过回环/内网/保留段，取第一个公网地址；
       全部为保留地址（如内网办公场景）时退回取最右（离本服务最近）一项。
    2. ``X-Real-IP``。
    3. ``request.client.host``（未经过反代的直连场景）。

    安全前提：所有能访问 API 的入口（前端 Nginx 及任何外层代理）都使用
    ``proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`` 追加真实
    对端地址，保证最右一项不可伪造。
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        entries = [e for e in (_clean_entry(x) for x in xff.split(",")) if e]
        if entries:
            for e in reversed(entries):
                if not _is_private(e):
                    return e[:64]
            return entries[-1][:64]
    x_real = request.headers.get("x-real-ip", "")
    if x_real:
        return _clean_entry(x_real)[:64]
    return request.client.host if request.client else ""


def get_user_agent(request: Request) -> str:
    """取 User-Agent：剔除控制字符并截断到 256 字符。"""
    ua = request.headers.get("user-agent", "")
    if not ua:
        return ""
    ua = "".join(ch for ch in ua if ch.isprintable())
    return ua[:256]
