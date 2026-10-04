"""报告「测试目标」数据计算：URL 来源优先级、根路径规范化与域名/IP 拆分。"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from app.core.outbound import resolve_host_ips


@dataclass(frozen=True)
class ReportTargetInfo:
    """测试目标表最终展示的三组值。"""

    urls: list[str]
    domains: list[str]
    ips: list[str]


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def _parse_url(raw: str | None):
    value = (raw or "").strip()
    if not value:
        return None
    # 存量资产/影响 URL 可能只填主机或 IP；补协议仅用于解析，不改变权威 URL 的展示值。
    candidate = value if "://" in value else f"http://{value}"
    try:
        return urlsplit(candidate)
    except ValueError:
        return None


def _format_netloc(host: str, port: int | None) -> str:
    try:
        if ipaddress.ip_address(host).version == 6:
            host = f"[{host}]"
    except ValueError:
        pass
    return f"{host}:{port}" if port is not None else host


def affected_url_root(raw: str | None) -> str | None:
    """影响 URL → 根路径 URL；非法或缺少主机的值返回 None。"""
    parsed = _parse_url(raw)
    if parsed is None or not parsed.hostname:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    scheme = (parsed.scheme or "http").lower()
    return urlunsplit((scheme, _format_netloc(parsed.hostname, port), "/", "", ""))


def split_affected_urls(raw: str | None) -> list[str]:
    """拆分漏洞影响 URL 的多行存储值。"""
    return [line.strip() for line in (raw or "").splitlines() if line.strip()]


def collect_asset_urls(assets: list[dict] | None) -> list[str]:
    """资产公网/内网 URL 的稳定去重集合。"""
    urls: list[str] = []
    for asset in assets or []:
        for item in asset.get("public_urls", []) or []:
            value = item.get("url") if isinstance(item, dict) else item
            if isinstance(value, str) and value.strip():
                urls.append(value.strip())
        for value in asset.get("internal_urls", []) or []:
            if isinstance(value, str) and value.strip():
                urls.append(value.strip())
    return _dedupe(urls)


def _hostname(raw: str | None) -> str | None:
    parsed = _parse_url(raw)
    if parsed is None or not parsed.hostname:
        return None
    return parsed.hostname.lower()


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def choose_target_urls(
    plan_urls: list[str] | None,
    asset_urls: list[str],
    affected_urls: list[str],
) -> list[str]:
    """按工单 URL → 资产 URL → 漏洞影响 URL 的优先级选择测试目标 URL。"""
    clean_plan = _dedupe([str(url).strip() for url in plan_urls or [] if str(url).strip()])
    if clean_plan:
        return clean_plan
    if asset_urls:
        return _dedupe(asset_urls)
    roots = [root for raw in affected_urls if (root := affected_url_root(raw))]
    return _dedupe(roots)


def _explicit_ips(raw: str | None) -> list[str]:
    return _dedupe([
        part.strip()
        for part in re.split(r"[\r\n,，]+", raw or "")
        if part.strip()
    ])


def _derived_ips(urls: list[str]) -> list[str]:
    ips: list[str] = []
    for url in urls:
        host = _hostname(url)
        if not host:
            continue
        if _is_ip_literal(host):
            ips.append(host)
            continue
        ips.extend(resolve_host_ips(host))
    return _dedupe(ips)


def build_target_info(
    *,
    meta: dict,
    assets: list[dict] | None,
    plan_urls: list[str] | None,
    vulns: list[dict] | None,
) -> ReportTargetInfo:
    """计算导出模板测试目标表的 URL、域名与 IP。"""
    affected_urls: list[str] = []
    for vuln in vulns or []:
        affected_urls.extend(split_affected_urls(vuln.get("affected_url")))
    urls = choose_target_urls(plan_urls, collect_asset_urls(assets), affected_urls)
    domains = _dedupe([
        host for url in urls
        if (host := _hostname(url)) and not _is_ip_literal(host)
    ])
    explicit_ips = _explicit_ips(str(meta.get("target_ip") or ""))
    return ReportTargetInfo(
        urls=urls,
        domains=domains,
        ips=explicit_ips or _derived_ips(urls),
    )
