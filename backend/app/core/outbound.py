"""服务端出站请求的目标校验（安全审计 TALOS-2026-003 修复，TALOS-2026-004 同源防护）。

用途：任何「目标地址来自用户输入」的服务端出站请求都必须先过本模块。当前接入点：
- 通知渠道 webhook（`schemas/system.py` 写入校验 + `workers/main.py` 发送前兜底校验）；
- 报告导出图片（现已改为「只内嵌 storage 内已本地化文件」，不再出站，见 report_builder）。

判定口径：协议限 http/https；主机为 IP 字面量时直接判定，为域名时解析**全部** A/AAAA 记录，
**任一**落入回环/私网/链路本地/共享地址/保留/组播段即拒绝（`VP_NOTIFY_HOST_ALLOWLIST`
中的主机可豁免，用于企业自建内网中继的显式放行）。禁用网段表在本模块内维护，与
`core/client_info.py`（客户端来源 IP 解析）各自独立、互不复用。

局限（如实记录，不夸大）：域名解析与实际建连之间存在 DNS 重绑定窗口（TOCTOU）。本模块在
「写入时」与「发送前」各校验一次以压缩该窗口；彻底消除需改为「解析出的 IP 直连 + 校验 Host 头」，
在需要支持 HTTPS 与 CDN 多 IP 的场景下代价较高，故未采用。
"""
import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import settings

# 禁止出站访问的 IPv4 地址段（回环/私网/链路本地/共享地址/文档与基准测试段/组播/保留）
_BLOCKED_NETS_V4 = tuple(ipaddress.ip_network(n) for n in (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/4",
    "240.0.0.0/4",
))

ALLOWED_SCHEMES = ("http", "https")


def _blocked_ip(ip: str) -> bool:
    """单个 IP 是否属于禁止出站的地址（IPv4 与 IPv6；IPv4-mapped 按 IPv4 判定）。"""
    addr = ipaddress.ip_address(ip)
    if addr.version == 6:
        if addr.ipv4_mapped is not None:
            addr = addr.ipv4_mapped
        else:
            return (
                addr.is_loopback or addr.is_link_local or addr.is_private
                or addr.is_multicast or addr.is_reserved or addr.is_unspecified
            )
    return any(addr in net for net in _BLOCKED_NETS_V4)


def allowlisted_hosts() -> set[str]:
    """显式放行的主机名（`VP_NOTIFY_HOST_ALLOWLIST`，逗号分隔，大小写不敏感）。"""
    return {
        h.strip().lower()
        for h in (settings.NOTIFY_HOST_ALLOWLIST or "").split(",")
        if h.strip()
    }


def resolve_host_ips(host: str) -> list[str]:
    """解析域名的全部 IP（A/AAAA）；无记录或解析失败返回空列表。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    return sorted({info[4][0] for info in infos})


def assert_public_url(url: str, *, field: str = "URL") -> str:
    """校验出站 URL 指向公网地址，通过则原样返回；否则抛 ValueError（中文文案）。

    校验顺序：格式（协议/主机）→ 主机白名单豁免 → IP 字面量判定 → 域名全量解析判定。
    DNS 解析失败（域名不存在 / 内网 DNS 不可达）一律拒绝，不做「解析失败即放行」的降级。
    """
    parsed = urlparse(url or "")
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError(f"{field}必须以 http:// 或 https:// 开头")
    host = parsed.hostname or ""
    if not host:
        raise ValueError(f"{field}缺少主机名")
    if host.lower() in allowlisted_hosts():
        return url
    try:
        if ipaddress.ip_address(host):
            ips = [host]
        else:
            ips = resolve_host_ips(host)
    except ValueError:
        raise ValueError(f"{field}主机格式非法：{host}") from None
    if not ips:
        raise ValueError(f"{field}主机无法解析：{host}")
    blocked = [ip for ip in ips if _blocked_ip(ip)]
    if blocked:
        raise ValueError(
            f"{field}指向内网/保留地址（{', '.join(blocked[:3])}）被拒绝；"
            "如确需访问内网中继，请加入 VP_NOTIFY_HOST_ALLOWLIST"
        )
    return url
