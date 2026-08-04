"""富文本 HTML 清洗：对所有入库的 *_html 字段做白名单过滤，防止存储型 XSS。

白名单标签/属性与前端 Tiptap 编辑器产出的结构对齐（段落、格式、列表、标题、
链接、图片、表格）。危险标签（script/iframe/style/on* 事件属性等）一律剔除。
"""
import nh3

# 允许保留的标签集合
_TAGS = {
    "p", "br", "span", "strong", "b", "em", "i", "s", "u", "code", "pre",
    "blockquote", "ul", "ol", "li", "h1", "h2", "h3", "h4",
    "a", "img", "table", "thead", "tbody", "tr", "td", "th",
}

# 各标签允许保留的属性（a 的 rel 由 nh3 通过 link_rel 自动管理，不在此声明）
_ATTRS = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "width", "height"},
    "span": {"style"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}

# 允许的 URL 协议（http/https/data，data 供富文本内嵌图片）
_URL_SCHEMES = {"http", "https", "data"}


def sanitize_html(html: str | None) -> str:
    """清洗富文本 HTML；空值原样返回。"""
    if not html:
        return html or ""
    return nh3.clean(html, tags=_TAGS, attributes=_ATTRS, url_schemes=_URL_SCHEMES)


# Excel/CSV 公式注入：单元格以这些字符开头时会被表格软件当作公式求值
EXCEL_FORMULA_PREFIXES = ("=", "+", "-", "@")


def excel_safe(value):
    """导出 Excel 时中和公式注入：对以 =/+/-/@ 开头的字符串前置单引号。
    非字符串（数字/日期/None 等）原样返回，不影响数值列。"""
    if isinstance(value, str) and value.startswith(EXCEL_FORMULA_PREFIXES):
        return "'" + value
    return value
