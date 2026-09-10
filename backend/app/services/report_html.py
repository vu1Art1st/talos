"""漏洞 → 报告章节 HTML 生成：报告路由与 Word 导入确认入库共用同一套章节结构。"""
import html as html_mod

from app.constants import VUL_LEVEL_EXPORT
from app.models import Vul

# 复测详情段在章节正文中的 HTML 标记（复测详情是独立编辑对象，不随章节快照内嵌）
RETEST_LABEL_HTML = "<p><strong>复测详情：</strong></p>"


def affected_urls_html(affected_url: str | None) -> str:
    """影响 URL 多值以换行分隔存储，逐条转义后换行展示。"""
    urls = [u.strip() for u in (affected_url or "").splitlines() if u.strip()]
    return "<br/>".join(html_mod.escape(u) for u in urls) or "-"


def strip_embedded_retest(content_html: str, retest_html: str = "") -> str:
    """剥离章节正文尾部内嵌的「复测详情」段（历史快照兼容）。

    早期 `vuln_section_html` 会把 `vul.retest_html` 追加为章节正文的最后一个元素，
    导致同一份复测详情既存在于章节快照、又存在于漏洞字段（界面重复展示）；
    且快照不会随复测更新，导出时还会因「已含复测详情」而跳过追加最新内容。

    剥离规则：
    - 仅处理正文中最后一次出现的复测详情标记（该段历史上恒位于正文末尾）；
    - 提供 retest_html 且正文尾部确以其开头时按精确边界剥离，保留其后手工追加的内容；
    - 否则丢弃标记之后的全部内容。
    """
    if not content_html or RETEST_LABEL_HTML not in content_html:
        return content_html or ""
    head, _, tail = content_html.rpartition(RETEST_LABEL_HTML)
    retest = (retest_html or "").strip()
    if retest and tail.strip().startswith(retest):
        return head + tail.strip()[len(retest):].strip()
    return head


def vuln_section_html(vul: Vul) -> str:
    """由漏洞记录生成标准章节 HTML，标签结构对齐导出模板「风险问题详情」（供报告编辑器继续编辑）。

    复测详情（`vul.retest_html`）不在此内嵌：它由复测处理面板单独维护，
    导出时由 report_builder._append_details 统一追加一次，保证「一个漏洞一份复测详情」
    且导出内容始终为最新（章节快照不会因复测更新而失效）。
    """
    parts = [
        f"<p><strong>测试状态：</strong>{'复测' if vul.is_retest else '初测'}</p>",
        f"<p><strong>漏洞等级：</strong>{VUL_LEVEL_EXPORT.get(vul.level, '-')}</p>",
        f"<p><strong>漏洞链接：</strong>{affected_urls_html(vul.affected_url)}</p>",
    ]
    if vul.description_html:
        parts.append(f"<p><strong>漏洞描述：</strong></p>{vul.description_html}")
    if vul.reproduce_html:
        parts.append(f"<p><strong>漏洞证明：</strong></p>{vul.reproduce_html}")
    if vul.solution_html:
        parts.append(f"<p><strong>修复建议：</strong></p>{vul.solution_html}")
    return "".join(parts)
