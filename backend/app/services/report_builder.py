"""报告 Word 构建：以渗透测试报告模板为基底，填充封面 / 版本记录 / 测试目标 / 汇总统计 / 漏洞详情。

模板锚点依赖 backend/app/templates/report_template.docx 的固定结构：
表0 封面装饰 | 表1 版本变更记录 | 表2 适用性声明 | 表3 目录(TOC 域)
表4 测试目标 | 表5 时间与人员 | 表6 风险问题汇总
"""
import copy
import html as _html_mod
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from docx.table import Table, _Row
from docx.text.paragraph import Paragraph
from htmldocx import HtmlToDocx
from pygments import lex
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.lexers.special import TextLexer
from pygments.token import Token

from app.constants import VUL_LEVEL_EXPORT, VUL_STATUS, VUL_TYPE, VulStatus
from app.core.config import settings
from app.core.timeutil import now as tznow  # 系统本地时间（UTC+8）；别名避免遮蔽模块内局部变量 now

_STORAGE_SRC = re.compile(r'src="/storage/([^"]+)"')
_HEADING_OPEN = re.compile(r"<h[1-6][^>]*>", re.IGNORECASE)
_HEADING_CLOSE = re.compile(r"</h[1-6]>", re.IGNORECASE)
# 章节快照中「测试状态：」后的初测/复测标记，导出时按漏洞最新 is_retest 重写
_TEST_STATE = re.compile(r"(测试状态：</strong>)\s*(?:初测|复测)")
# 代码块：<pre>/<code> 中的换行转 <br/>、缩进空格转 &nbsp;，保证 Word 中保留格式。
# 同时匹配已转义的 &lt;code&gt;/&lt;pre&gt;（富文本粘贴/Word 导入等场景会把标签存成实体），
# 避免 Word 中直接显示 `<code>21</code>` 原始标签。
_REAL_PRE_BLOCK = re.compile(r"<pre[^>]*>(.*?)</pre>", re.DOTALL | re.IGNORECASE)
_REAL_CODE_BLOCK = re.compile(r"<code[^>]*>(.*?)</code>", re.DOTALL | re.IGNORECASE)
_ESC_PRE_BLOCK = re.compile(r"&lt;pre[^&]*&gt;(.*?)&lt;/pre&gt;", re.DOTALL | re.IGNORECASE)
_ESC_CODE_BLOCK = re.compile(r"&lt;code[^&]*&gt;(.*?)&lt;/code&gt;", re.DOTALL | re.IGNORECASE)
# 超链接标签剥离：仅保留链接文字（需求13：URL 以普通文本展示）
_LINK_OPEN = re.compile(r"<a\s+[^>]*>", re.IGNORECASE)
_LINK_CLOSE = re.compile(r"</a>", re.IGNORECASE)

# 汇总表「问题等级」字体颜色，与模板统计段落（超危/高危/中危/低危漏洞N个）保持一致
_LEVEL_COLORS = {
    "超危": RGBColor(0xC0, 0x00, 0x00),
    "高危": RGBColor(0xFF, 0x00, 0x00),
    "中危": RGBColor(0xFF, 0xC0, 0x00),
    "低危": RGBColor(0x00, 0x70, 0xC0),
}

# 汇总表「问题状态」已修复漏洞的绿色
FIXED_STATUS_COLOR = RGBColor(0x00, 0xB0, 0x50)

# 模板中用于定位替换的封面/统计段落文案
_TPL_COVER_TITLE = "标准名称（邮件、台账）-系统名称（网页）"
_TPL_COVER_DATE = "2026年xx月xx日"
_TPL_COMPANY = "中移系统集成有限公司"


def _localize_images(html: str) -> str:
    """把 /storage/xx 图片 URL 替换为本地文件路径，供 htmldocx 内嵌图片。

    仅接受解析后仍位于 storage 根目录内的路径，防止 ../ 路径遍历读取任意文件；
    越界路径保持原样（本地无此文件将被后续降级处理跳过）。"""
    base = settings.storage_path.resolve()

    def repl(m: re.Match) -> str:
        candidate = (settings.storage_path / m.group(1)).resolve()
        if not candidate.is_relative_to(base):
            return m.group(0)
        return f'src="{candidate.as_posix()}"'

    return _STORAGE_SRC.sub(repl, html or "")


def _demote_headings(html: str) -> str:
    """正文富文本中的 h1-h6 降级为加粗段落，确保目录层级仅由模板章节标题构成
    （一级：二、测试结果综述 / 二级：2.1、风险问题汇总 / 三级：2.2.1、漏洞标题）。"""
    html = _HEADING_OPEN.sub("<p><strong>", html or "")
    return _HEADING_CLOSE.sub("</strong></p>", html)


# ---------- 代码块：pygments 语法高亮 + 等宽样式（导出到 Word 保持格式） ----------

# 代码块等宽字体；eastAsia 用于代码中的中文注释，避免中文字符走默认字体
_CODE_FONT = "Consolas"
_CODE_EAST_FONT = "Microsoft YaHei"
# 代码块底纹与边框（GitHub 风格浅灰）
_CODE_BG = "F6F8FA"
_CODE_BORDER = "D0D7DE"
# 高亮配色（GitHub 风格）：(父 token 类型, 十六进制颜色, 是否斜体)
_CODE_TOKEN_STYLE = [
    (Token.Comment, "6A737D", True),          # 注释：灰 + 斜体
    (Token.Literal.String, "032F62", False),  # 字符串：深蓝
    (Token.Literal.Number, "005CC5", False),  # 数字：蓝
    (Token.Keyword, "D73A49", False),         # 关键字：红
    (Token.Name.Function, "6F42C1", False),   # 函数名：紫
    (Token.Name.Class, "6F42C1", False),      # 类名：紫
    (Token.Name.Builtin, "005CC5", False),    # 内置名：蓝
    (Token.Name.Namespace, "6F42C1", False),
    (Token.Name.Constant, "005CC5", False),
    (Token.Name.Decorator, "D73A49", False),  # 装饰器：红
    (Token.Operator, "D73A49", False),        # 运算符：红
    (Token.Generic, "24292E", False),
]
_CODE_DEFAULT_COLOR = "24292E"

_LANG_CLASS = re.compile(
    r'class\s*=\s*["\']?(?:language|lang|brush)[:-]\s*([A-Za-z0-9_+#-]+)', re.IGNORECASE
)


def _extract_lang(tag: str) -> str:
    """从 <pre>/<code> 标签 class 中提取语言名，如 language-python → python。"""
    m = _LANG_CLASS.search(tag)
    return m.group(1).lower() if m else ""


def _token_style(ttype) -> tuple[str, bool]:
    """按 pygments token 类型返回 (颜色, 是否斜体)，未匹配则用默认黑色。"""
    for parent, color, italic in _CODE_TOKEN_STYLE:
        if ttype in parent:
            return color, italic
    return _CODE_DEFAULT_COLOR, False


def _resolve_lexer(code: str, lang: str):
    """解析代码块语言：
    - 显式语言标记优先；否则代码足够长（>60 字符）时用 guess_lexer 猜测，
      避免把 `' or 1=1--` 之类的短片段误判；均失败时退回纯文本 lexer。
    """
    if lang:
        try:
            return get_lexer_by_name(lang, stripnl=False)
        except Exception:
            pass
    if len(code.strip()) > 60:
        try:
            return guess_lexer(code, stripnl=False)
        except Exception:
            pass
    return TextLexer(stripnl=False)


def _split_token_lines(tokens: list[tuple]) -> list[list[tuple]]:
    """把 pygments token 流按换行拆分为多行。"""
    lines: list[list[tuple]] = [[]]
    for ttype, value in tokens:
        while True:
            idx = value.find("\n")
            if idx < 0:
                if value:
                    lines[-1].append((ttype, value))
                break
            head, value = value[:idx], value[idx + 1:]
            if head:
                lines[-1].append((ttype, head))
            lines.append([])
    return lines


def _style_code_run(run, ttype) -> None:
    """代码 run：等宽字体 + 按 token 类型着色。"""
    color, italic = _token_style(ttype)
    run.font.name = _CODE_FONT
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), _CODE_EAST_FONT)
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor.from_string(color)
    run.italic = italic


def _style_code_para(p: Paragraph) -> None:
    """代码块段落：浅灰底纹 + 单线边框 + 紧凑行距，整体呈代码块外观。"""
    pf = p.paragraph_format
    pf.left_indent = Cm(0.4)
    pf.right_indent = Cm(0.2)
    pf.space_before = Pt(3)
    pf.space_after = Pt(3)
    pf.line_spacing = 1.0
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    for side in ("top", "left", "bottom", "right"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:space"), "3")
        b.set(qn("w:color"), _CODE_BORDER)
        pBdr.append(b)
    pPr.append(pBdr)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), _CODE_BG)
    pPr.append(shd)


def _add_code_block(doc: Document, code: str, lang: str) -> None:
    """把代码渲染为一个带边框底纹的段落：行内换行用 w:br，token 逐个着色。"""
    lexer = _resolve_lexer(code, lang)
    try:
        tokens = list(lex(code, lexer))
    except Exception:
        tokens = [(Token.Text, code)]
    lines = _split_token_lines(tokens)
    p = doc.add_paragraph()
    _style_code_para(p)
    first = True
    for line in lines:
        if not first:
            p.add_run().add_break()
        first = False
        for ttype, value in line:
            run = p.add_run(value)
            _style_code_run(run, ttype)


def _esc_code_to_real(m: re.Match) -> str:
    """转义实体 &lt;code&gt;：多行还原为 <pre> 代码块，单行还原为真 <code> 标签。"""
    content = m.group(1)
    if "\n" in content or "<br" in content.lower():
        return f"<pre>{content}</pre>"
    return f"<code>{content}</code>"


def _strip_code_wrap(inner: str) -> str:
    """去掉 <pre> 内容外层可能存在的 <code> 包裹标签。"""
    inner = re.sub(r"^\s*<code[^>]*>", "", inner, count=1)
    inner = re.sub(r"</code>\s*$", "", inner, count=1)
    return inner.strip()


def _split_inline_codes(fragment: str) -> list[tuple[str, str, str]]:
    """把 <pre> 之外的片段按多行 <code> 再分割（提升为代码块）。

    单行行内 <code> 不分割、保留在 html 片段中（htmldocx 以等宽字体渲染），
    避免 tiptap/Word 常见 `<pre><code>...</code></pre>` 结构被二次处理。"""
    parts: list[tuple[str, str, str]] = []
    last = 0
    for m in _REAL_CODE_BLOCK.finditer(fragment):
        content = m.group(1)
        if "\n" not in content and "<br" not in content.lower():
            continue  # 单行 code 留在 html 段
        if m.start() > last:
            parts.append(("html", fragment[last:m.start()], ""))
        parts.append(("code", _html_mod.unescape(content), _extract_lang(m.group(0))))
        last = m.end()
    if not parts:
        return [("html", fragment, "")]
    if last < len(fragment):
        parts.append(("html", fragment[last:], ""))
    return parts


def _split_blocks(html: str) -> list[tuple[str, str, str]]:
    """把富文本 HTML 分割为交替的 html / code 片段。

    返回 [(kind, content, lang)]，kind ∈ {"html", "code"}：
    - 真标签 <pre>、多行 <code> 以及转义实体 &lt;pre&gt;/&lt;code&gt;（多行）识别为代码块；
    - 单行行内 <code> 保留在 html 片段中，由 htmldocx 以等宽字体渲染。
    """
    html = html or ""
    # 1) 转义实体还原（富文本粘贴 / Word 导入会把标签存成 &lt;...&gt;）
    html = _ESC_PRE_BLOCK.sub(lambda m: f"<pre>{m.group(1)}</pre>", html)
    html = _ESC_CODE_BLOCK.sub(_esc_code_to_real, html)
    # 2) 按 <pre> 分割（<pre> 内部的 <code> 在提取时剥掉，避免嵌套 pre）
    parts: list[tuple[str, str, str]] = []
    pos = 0
    for m in _REAL_PRE_BLOCK.finditer(html):
        if m.start() > pos:
            parts.extend(_split_inline_codes(html[pos:m.start()]))
        parts.append((
            "code",
            _html_mod.unescape(_strip_code_wrap(m.group(1))),
            _extract_lang(m.group(0)),
        ))
        pos = m.end()
    if pos < len(html):
        parts.extend(_split_inline_codes(html[pos:]))
    return parts or [("html", html, "")]


def _strip_links(html: str) -> str:
    """剥离 <a href> 超链接标签，仅保留链接文字（需求13：URL 以普通文本展示）。"""
    return _LINK_CLOSE.sub("", _LINK_OPEN.sub("", html or ""))


def _color_vuln_levels(html: str) -> str:
    """漏洞章节中的「漏洞等级：」文字着色，颜色与风险汇总一致（需求14）。

    使用 htmldocx 支持的 <span style="color: #rrggbb"> 内联样式（其 color 处理
    支持 #hex 形式），将「漏洞等级：高危」等文字染上与风险汇总一致的颜色。"""
    for label, color in _LEVEL_COLORS.items():
        # 仅处理「漏洞等级：」后紧跟该等级文字的片段，避免误伤正文
        html = re.sub(
            rf"(<strong>漏洞等级：</strong>)\s*{label}",
            rf'\g<1><span style="color: #{color}">{label}</span>',
            html,
        )
    return html


def _number_vuln_urls(html: str) -> str:
    """漏洞章节「漏洞链接：」内容排版（需求14/需求3）。

    - 链接一律另起一行展示（不在「漏洞链接：」标签后紧跟）；
    - 单个链接直接换行展示；多个链接自动编号并按行排列。"""
    def _repl(m: re.Match) -> str:
        urls = [u.strip() for u in re.split(r"<br\s*/?>", m.group(2)) if u.strip()]
        if not urls:
            return m.group(0)
        if len(urls) == 1:
            # 单个链接：另起一行，不带编号
            return f"{m.group(1)}<br/>{urls[0]}"
        numbered = "<br/>".join(f"{i}. {u}" for i, u in enumerate(urls, 1))
        return f"{m.group(1)}<br/>{numbered}"

    return re.sub(
        r"(<strong>漏洞链接：</strong>)(.*?)(</p>)",
        _repl,
        html or "",
        flags=re.DOTALL,
    )


def _add_html(doc: Document, html: str) -> None:
    html = _localize_images(_demote_headings(html or ""))
    for kind, content, lang in _split_blocks(html):
        if kind == "code":
            try:
                _add_code_block(doc, content, lang)
            except Exception:
                # 高亮失败时降级为无高亮的等宽纯文本代码块
                _add_code_block(doc, content, "")
            continue
        text = _strip_links(content)
        if not text.strip():
            continue
        parser = HtmlToDocx()
        try:
            parser.add_html_to_document(text, doc)
        except Exception:
            # 富文本转换失败时降级为纯文本，避免导出整体失败
            plain = re.sub(r"<[^>]+>", "", text)
            doc.add_paragraph(plain)


def _set_para_text(para: Paragraph, text: str) -> None:
    """替换段落文本并保留首个 run 的字体格式。"""
    if para.runs:
        para.runs[0].text = text
        for run in para.runs[1:]:
            run.text = ""
    else:
        para.add_run(text)


def _set_cell_text(cell, text: str) -> None:
    """替换单元格文本，保留原格式；多余段落清除。"""
    for extra in cell.paragraphs[1:]:
        extra._element.getparent().remove(extra._element)
    _set_para_text(cell.paragraphs[0], text)


def _clone_row(table: Table, src_row: _Row) -> _Row:
    """深拷贝样例行（保留边框/字体等格式）并追加到表尾。"""
    new_tr = copy.deepcopy(src_row._tr)
    src_row._tr.getparent().append(new_tr)
    return table.rows[-1]


def _fill_cover(doc: Document, meta: dict, now: datetime) -> None:
    system_name = meta.get("project_name") or meta.get("title") or "渗透测试报告"
    for para in doc.paragraphs:
        text = para.text.strip()
        if text == _TPL_COVER_TITLE:
            # 封面第二行 = 系统名称（上一行为公司名、下两行为“渗透测试/报告”）
            _set_para_text(para, system_name)
        elif text == _TPL_COVER_DATE:
            _set_para_text(para, now.strftime("%Y年%m月%d日"))
        elif text == _TPL_COMPANY and meta.get("customer"):
            _set_para_text(para, meta["customer"])
            # 只替换封面首个公司名段落，统计段等由各自逻辑处理
            break


def _fill_applicability(doc: Document, meta: dict) -> None:
    """适用性声明（模板表2）：将系统名称占位符「xxxxx系统」替换为实际系统名称。

    模板中占位符为独立 run，直接替换即可保留其余文字与格式；若占位符跨 run
    （模板结构变化），则整段合并重写并保留首 run 格式。"""
    system_name = meta.get("project_name") or meta.get("title") or ""
    if not system_name:
        return
    para = doc.tables[2].rows[1].cells[0].paragraphs[0]
    for run in para.runs:
        if "xxxxx系统" in run.text:
            run.text = run.text.replace("xxxxx系统", system_name)
            return
    # 跨 run 兜底：拼接整段替换后重写
    full = "".join(r.text for r in para.runs)
    if "xxxxx系统" in full:
        _set_para_text(para, full.replace("xxxxx系统", system_name))


def _version_records(meta: dict, now: datetime, vulns: list[dict]) -> list[dict]:
    """按测试阶段生成版本变更记录序列：
    初测 = V1.0「初测创建」；第一轮复测 = V2.0「复测创建」；
    第二轮起：修改人与上一轮相同则次版本 +1（V2.1），变更则升级主版本（V3.0）。"""
    records = [{
        "date": meta.get("report_create_date") or now.strftime("%Y-%m-%d"),
        "version": "V1.0",
        "note": "初测创建",
        "author": meta.get("author", ""),
    }]
    rounds = meta.get("retest_rounds") or []
    if not rounds and any(v.get("is_retest") for v in vulns):
        # 无计划轮次数据但存在复测漏洞时，V1.0 标记为复测更新（兼容旧行为）
        records[0]["note"] = "复测更新"
    major, minor = 1, 0
    prev_creator = ""
    for idx, r in enumerate(rounds, start=1):
        creator = (r.get("creator_name") or "").strip()
        if idx == 1:
            major, minor = 2, 0
            note = "复测创建"
        else:
            if creator and creator == prev_creator:
                minor += 1
            else:
                major, minor = major + 1, 0
            note = "复测更新"
        records.append({
            "date": r.get("date") or now.strftime("%Y-%m-%d"),
            "version": f"V{major}.{minor}",
            "note": note,
            "author": creator or meta.get("author", ""),
        })
        prev_creator = creator
    return records


def _fill_version_table(doc: Document, meta: dict, vulns: list[dict], now: datetime) -> None:
    table = doc.tables[1]
    records = _version_records(meta, now, vulns)
    sample = table.rows[2]
    for i, rev in enumerate(records):
        if i < len(table.rows) - 2:
            row = table.rows[2 + i]
        else:
            row = _clone_row(table, sample)
        values = [rev["date"], rev["version"], rev["note"], "内部使用", rev["author"]]
        for cell, value in zip(row.cells, values):
            _set_cell_text(cell, value)


def _fill_target_table(doc: Document, meta: dict, assets: list[dict]) -> None:
    table = doc.tables[4]
    urls: list[str] = []
    for a in assets:
        urls.extend(u.get("url", "") for u in a.get("public_urls", []) if isinstance(u, dict))
        urls.extend(a.get("internal_urls", []))
    urls = [u for u in dict.fromkeys(urls) if u]
    domains = list(dict.fromkeys(
        h for u in urls if (h := urlparse(u if "://" in u else f"http://{u}").hostname)
    ))
    system_names = list(dict.fromkeys(a.get("name", "") for a in assets if a.get("name")))

    _set_cell_text(table.rows[0].cells[1], meta.get("project_name") or "、".join(system_names) or meta.get("title", ""))
    _set_cell_text(table.rows[1].cells[1], "\n".join(urls))
    _set_cell_text(table.rows[2].cells[1], "\n".join(domains))
    _set_cell_text(table.rows[3].cells[1], meta.get("target_ip", ""))
    # rows[4] 被测测试账号：系统无对应数据，留空由人工补充


def _fill_schedule_table(doc: Document, meta: dict) -> None:
    table = doc.tables[5]
    _set_cell_text(table.rows[1].cells[1], meta.get("test_start", ""))
    _set_cell_text(table.rows[1].cells[3], meta.get("test_end", ""))
    # 参测人员：一人独立占一个单元格（模板 row4 起为 总负责人/执行测试 行）
    testers = meta.get("testers") or []
    if not testers and meta.get("author"):
        testers = [meta["author"]]
    if not testers:
        return
    sample = table.rows[5]
    rows = list(table.rows[4:])
    for i, name in enumerate(testers):
        if i >= len(rows):
            rows.append(_clone_row(table, sample))
        _set_cell_text(rows[i].cells[0], name)
    # 清空多余模板行的参测人员名，避免残留
    for row in rows[len(testers):]:
        _set_cell_text(row.cells[0], "")


def _set_summary_first_para(para: Paragraph, company: str, system_name: str) -> None:
    """2.1 风险问题汇总首段：「经本次测试，{company}{system_name}共发现：」
    仅系统名称加粗，其余文字保持模板原格式。

    模板中系统名（xxx系统）为独立 run，找到后仅替换其文本并设置加粗；
    若 run 结构不符合预期（未找到系统名 run），兜底整段重写（不保证加粗）。"""
    if not para.runs:
        para.add_run(f"经本次测试，{company}{system_name}共发现：")
        return
    para.runs[0].text = f"经本次测试，{company}"
    for run in para.runs[1:]:
        if "系统" in run.text:
            run.text = system_name
            run.bold = True
            return
    _set_para_text(para, f"经本次测试，{company}{system_name}共发现：")


def _fill_summary(doc: Document, meta: dict, vulns: list[dict]) -> None:
    """重写「风险问题汇总」统计段落与汇总表。"""
    counts = {"超危": 0, "高危": 0, "中危": 0, "低危": 0}
    for v in vulns:
        # 统计段仅计入当前未修复漏洞（状态非已修复）
        if v.get("status") == VulStatus.FIXED:
            continue
        label = VUL_LEVEL_EXPORT.get(v.get("level"))
        if label in counts:
            counts[label] += 1
    system_name = meta.get("project_name") or meta.get("title", "")
    company = meta.get("customer") or _TPL_COMPANY

    lines = list(counts.items())
    for para in doc.paragraphs:
        text = para.text.strip()
        if text.startswith("经本次测试"):
            _set_summary_first_para(para, company, system_name)
        else:
            for i, (label, num) in enumerate(lines):
                if text.startswith(f"{label}漏洞"):
                    tail = "。" if i == len(lines) - 1 else "，"
                    _set_para_text(para, f"{label}漏洞{num}个{tail}")
                    break

    table = doc.tables[6]
    sample = table.rows[1]
    for v in vulns:
        row = _clone_row(table, sample)
        values = [
            VUL_LEVEL_EXPORT.get(v.get("level"), "-"),
            VUL_TYPE.get(v.get("vul_type"), "其他"),
            v.get("title", ""),
            VUL_STATUS.get(v.get("status"), "-"),
        ]
        for cell, value in zip(row.cells, values):
            _set_cell_text(cell, value)
        # 问题等级字体颜色对齐上方统计段落中对应等级的颜色
        color = _LEVEL_COLORS.get(values[0])
        if color is not None:
            for run in row.cells[0].paragraphs[0].runs:
                run.font.color.rgb = color
        # 已修复漏洞状态列显示为绿色
        if v.get("status") == VulStatus.FIXED:
            for run in row.cells[3].paragraphs[0].runs:
                run.font.color.rgb = FIXED_STATUS_COLOR
    if not vulns:
        for cell in sample.cells:
            _set_cell_text(cell, "")
    else:
        sample._tr.getparent().remove(sample._tr)


def _remove_sample_details(doc: Document) -> None:
    """删除模板「风险问题详情」小节下的样例漏洞内容（H3 起至文末）。"""
    body = doc.element.body
    found_h2 = False
    removing = False
    for child in list(body.iterchildren()):
        if child.tag == qn("w:sectPr"):
            continue
        if not removing and child.tag == qn("w:p"):
            para = Paragraph(child, doc)
            if not found_h2 and para.text.strip() == "风险问题详情":
                found_h2 = True
                continue
            if found_h2 and para.style.name == "Heading 3":
                removing = True
        if removing:
            body.remove(child)


def _apply_field_spacing(doc: Document, start: int) -> None:
    """风险问题详情章节正文段落统一 1.5 倍行距（章节标题除外）。

    覆盖漏洞描述/证明/修复建议/复测详情等具体内容段落，保证阅读舒适。"""
    for para in doc.paragraphs[start:]:
        if para.style.name.startswith("Heading"):
            continue
        if para.text.strip():
            para.paragraph_format.line_spacing = 1.5


def _append_details(doc: Document, vulns: list[dict], sections: list[dict]) -> None:
    by_id = {v.get("id"): v for v in vulns}
    if not sections:
        doc.add_paragraph("本次报告未关联漏洞记录。")
        return
    for section in sections:
        vul = by_id.get(section.get("vul_id"))
        title = section.get("title") or "未命名章节"
        content_html = section.get("content_html", "")
        if vul is not None:
            # 测试状态：按漏洞最新 is_retest 重写快照（复测未通过也属于复测）
            state = "复测" if vul.get("is_retest") else "初测"
            content_html = _TEST_STATE.sub(rf"\g<1>{state}", content_html)
            # 漏洞等级颜色与风险汇总一致、漏洞链接逐条编号另起一行（需求14）
            content_html = _color_vuln_levels(content_html)
            content_html = _number_vuln_urls(content_html)
            # 修复中且经历过复测 = 复测未通过打回，展示层区分（状态码不变）
            status_name = VUL_STATUS.get(vul.get("status"), "-")
            if vul.get("status") == VulStatus.FIXING and vul.get("is_retest"):
                status_name = "复测未通过"
            title = f"{title}（{status_name}）"
        doc.add_paragraph(title, style="Heading 3")
        body_start = len(doc.paragraphs)
        _add_html(doc, content_html)
        # 章节快照未含复测详情时，追加漏洞最新复测内容（避免与生成时嵌入的快照重复）
        retest = (vul or {}).get("retest_html", "")
        if retest and "复测详情" not in (content_html or ""):
            _add_html(doc, f"<p><strong>复测详情：</strong></p>{retest}")
        _apply_field_spacing(doc, body_start)


def _build_toc_field(doc: Document) -> None:
    """恢复模板表3中的 TOC 域（回退方案：目录由 Word/WPS/LibreOffice 打开时刷新）。

    模板表3 结构：row0 =「目录」标题，row1 = TOC 域单元格。这里清空 row1 中
    缓存的旧目录条目，重建一个干净的 TOC 域（w:fldChar begin/instrText/separate/end）：
    - 域指令 `TOC \\o "1-3" \\h \\z \\u`：收录 1-3 级内置标题、条目带超链接、
      隐藏制表符前导符、按大纲级别收集；
    - separate 后保留一段提示占位文本，打开文档更新域后会被真实目录替换；
    - 配合 _enable_update_fields（w:updateFields=true）让 Word/WPS 打开时自动刷新。
    """
    table = doc.tables[3]
    if len(table.rows) < 2:
        return
    toc_cell = table.rows[1].cells[0]
    # 清空原 TOC 域所在单元格的全部段落（含缓存的目录条目）
    for p in list(toc_cell.paragraphs):
        p._element.getparent().remove(p._element)
    para = toc_cell.add_paragraph()
    run = para.add_run()
    r_el = run._r
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = ' TOC \\o "1-3" \\h \\z \\u '
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    # 未更新域前的占位提示；打开文档按 F9 / 右键目录「更新域」即替换为真实目录
    placeholder = OxmlElement("w:t")
    placeholder.set(qn("xml:space"), "preserve")
    placeholder.text = "（目录占位：打开文档后右键目录 → 更新域，或按 F9 刷新生成完整目录）"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    for el in (begin, instr, separate, placeholder, end):
        r_el.append(el)


def _enable_update_fields(doc: Document) -> None:
    """标记打开文档时刷新域，Word 会自动更新目录页码。

    w:updateFields 必须位于 CT_Settings 规定的早期位置（在 hdrShapeDefaults / footnotePr /
    endnotePr / compat / rsids 等之前），否则 Word 会忽略该设置导致打开不刷新目录。"""
    element = doc.settings.element
    if element.find(qn("w:updateFields")) is not None:
        return
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    # 定位首个“应排在 updateFields 之后”的元素，插入其前；均不存在时追加到末尾
    anchor_tags = (
        "w:hdrShapeDefaults", "w:footnotePr", "w:endnotePr",
        "w:compat", "w:rsids", "m:mathPr", "w:themeFontLang",
    )
    anchor = None
    for child in element:
        if child.tag in {qn(t) for t in anchor_tags}:
            anchor = child
            break
    if anchor is not None:
        anchor.addprevious(update)
    else:
        element.append(update)


def _fit_images(doc: Document, max_width_cm: float = 15.0) -> None:
    """将超过版心宽度的内联图片等比缩小，确保 Word 打开后完整显示。

    仅调整过宽的图片，小图尺寸保持不变；比例按宽度同比缩放，避免变形。"""
    max_width = Cm(max_width_cm)
    for shape in doc.inline_shapes:
        w, h = shape.width, shape.height
        if w and w > max_width:
            shape.width = max_width
            if h:
                shape.height = int(h * (max_width / w))


def build_report_docx(
    meta: dict,
    vulns: list[dict],
    sections: list[dict],
    out_path: str,
    assets: list[dict] | None = None,
) -> str:
    """基于模板生成报告 docx。

    meta: 报告元信息；vulns: 漏洞数据（含 id/level/status 等）；
    sections: [{title, content_html, vul_id}] 有序章节；assets: 关联资产聚合。
    """
    template = Path(settings.REPORT_TEMPLATE)
    if not template.exists():
        raise FileNotFoundError(f"报告模板不存在: {template}")

    doc = Document(str(template))
    now = tznow()

    _fill_cover(doc, meta, now)
    _fill_applicability(doc, meta)
    _fill_version_table(doc, meta, vulns, now)
    _fill_target_table(doc, meta, assets or [])
    _fill_schedule_table(doc, meta)
    _fill_summary(doc, meta, vulns)
    _remove_sample_details(doc)
    _append_details(doc, vulns, sections)
    _build_toc_field(doc)
    _fit_images(doc)
    _enable_update_fields(doc)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return out_path
