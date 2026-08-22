"""漏洞 → 报告章节 HTML 生成：报告路由与 Word 导入确认入库共用同一套章节结构。"""
import html as html_mod

from app.constants import VUL_LEVEL_EXPORT
from app.models import Vul


def affected_urls_html(affected_url: str | None) -> str:
    """影响 URL 多值以换行分隔存储，逐条转义后换行展示。"""
    urls = [u.strip() for u in (affected_url or "").splitlines() if u.strip()]
    return "<br/>".join(html_mod.escape(u) for u in urls) or "-"


def vuln_section_html(vul: Vul) -> str:
    """由漏洞记录生成标准章节 HTML，标签结构对齐导出模板「风险问题详情」（供报告编辑器继续编辑）。"""
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
    if vul.retest_html:
        parts.append(f"<p><strong>复测详情：</strong></p>{vul.retest_html}")
    return "".join(parts)
