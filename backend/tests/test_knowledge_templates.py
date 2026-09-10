"""漏洞模板库数据文件（knowledge-import-vulnerabilities.json）完整性测试。

模板库以该 JSON 为唯一权威数据源（scripts.seed_knowledge 与
scripts.sync_knowledge_templates 均消费它），本测试固化「命名规范 / 内容质量 /
组件漏洞拆分 / 参考链接来源」四类要求，防止后续改动回退。
"""
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from app.constants import VUL_LEVEL, VUL_TYPE

DATA_FILE = Path(__file__).resolve().parents[1] / "knowledge-import-vulnerabilities.json"

# 安全社区 / 厂商威胁情报 / 官方漏洞库，作为有 CVE 条目的参考来源白名单
_COMMUNITY_DOMAINS = (
    "xz.aliyun.com",      # 先知社区
    "freebuf.com",        # FreeBuf
    "butian.net",         # 奇安信攻防社区
    "anquanke.com",       # 安全客
    "secrss.com",         # 安全内参（奇安信）
    "nsfocus.net",        # 绿盟科技
    "venustech.com.cn",   # 启明星辰 CERT
    "huaweicloud.com",    # 华为云安全公告
    "aliyun.com",         # 阿里云安全
    "tencent.com",        # 腾讯安全
    "cn-sec.com",         # CN-SEC 中文网
    "nvd.nist.gov",       # NVD
)


@pytest.fixture(scope="module")
def entries() -> list[dict]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _plain(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()


def test_names_unique_and_dict_codes(entries: list[dict]) -> None:
    """条目规模、名称唯一性与字典码合法性。"""
    assert len(entries) >= 60, "模板库条目过少，可能数据文件被截断"
    names = [e["vulnerability_name"] for e in entries]
    dup = [n for n, c in Counter(names).items() if c > 1]
    assert not dup, f"漏洞名称重复：{dup}"
    for e in entries:
        assert e["vul_type"] in VUL_TYPE, f"{e['vulnerability_name']} 漏洞类型码非法"
        assert e["severity_level"] in VUL_LEVEL, f"{e['vulnerability_name']} 危害等级码非法"


def test_content_quality_and_numbered_solutions(entries: list[dict]) -> None:
    """描述/危害不得过于简单；修复建议多条时须按 1、2、3 编号换行。"""
    for e in entries:
        name = e["vulnerability_name"]
        assert len(_plain(e["description_html"])) >= 30, f"{name} 标准描述过短"
        assert len(_plain(e["harm_html"])) >= 15, f"{name} 危害说明过短"
        paras = re.findall(r"<p>(.*?)</p>", e["solution_html"])
        assert len(paras) >= 2, f"{name} 修复建议应分条列出"
        for i, para in enumerate(paras, start=1):
            assert para.startswith(f"{i}、"), f"{name} 修复建议第 {i} 条缺少「{i}、」编号"


def test_references_are_http_urls(entries: list[dict]) -> None:
    for e in entries:
        refs = e.get("references") or []
        assert refs, f"{e['vulnerability_name']} 缺少参考链接"
        for url in refs:
            assert url.startswith(("http://", "https://")), f"{e['vulnerability_name']} 参考链接非法：{url}"


def test_cve_appended_to_name(entries: list[dict]) -> None:
    """有明确 CVE 编号的漏洞，名称须以「（CVE-YYYY-NNNN）」结尾。"""
    for e in entries:
        name = e["vulnerability_name"]
        if "CVE-" in name:
            assert re.search(r"（CVE-\d{4}-\d{4,7}）$", name), f"{name} CVE 编号格式不规范"


def test_multi_vuln_components_are_split(entries: list[dict]) -> None:
    """nacos / shiro / fastjson 等多漏洞组件须按漏洞拆分，禁止合并为一条。"""
    names = {e["vulnerability_name"] for e in entries}
    for merged in ("Fastjson反序列化", "Shiro反序列化", "Nacos权限绕过/默认密钥"):
        assert merged not in names, f"仍存在多漏洞合并条目：{merged}"
    for expected in (
        "Fastjson 1.2.24反序列化命令执行（CVE-2017-18349）",
        "Fastjson autoType绕过命令执行（CVE-2022-25845）",
        "Apache Shiro rememberMe反序列化命令执行（CVE-2016-4437）",
        "Apache Shiro认证绕过（CVE-2020-1957）",
        "Nacos权限绕过（CVE-2021-29441）",
        "Nacos默认密钥权限绕过（QVD-2023-6271）",
    ):
        assert expected in names, f"缺少拆分后的条目：{expected}"


def test_cve_entries_cite_security_community(entries: list[dict]) -> None:
    """有 CVE 编号的条目，参考链接须包含安全社区 / 厂商情报 / 官方漏洞库来源。"""
    for e in entries:
        if "CVE-" not in e["vulnerability_name"]:
            continue
        assert any(
            domain in url for url in e["references"] for domain in _COMMUNITY_DOMAINS
        ), f"{e['vulnerability_name']} 参考链接缺少安全社区/厂商来源"
