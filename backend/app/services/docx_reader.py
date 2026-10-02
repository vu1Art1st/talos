"""`lxml.iterparse` 自写 docx reader（批次 E-2 Phase 1）。

只替换**数据访问层**：本模块提供一个与 python-docx 同名同义的只读门面
（`Document.paragraphs` / `.tables` / `.part`），供 `services/docx_parser.py` 复用；
标签匹配、等级映射、HTML 拼接等业务逻辑保持单源不动。

行为契约逐条对齐 python-docx（`docs/ROADMAP.md` 6.4.2）：

1. `paragraphs` / `tables` 只取 `w:body` 直接子元素（嵌套表、表格内段落都不进入）；
2. `p.runs` 只取 `w:p` 直接子 `w:r`，而 `p.text` 额外包含 `w:hyperlink` 的可见文字
   （python-docx 的 `CT_P.text` 走 `w:r | w:hyperlink`，两者口径本就不同）；
3. `run.text` 由 `w:br|w:cr|w:noBreakHyphen|w:ptab|w:t|w:tab` 合成（`w:br` 仅
   `type=textWrapping` 记换行）；
4. `bold` / `italic` 只读 `w:rPr/w:b|w:i`：缺省 None，`w:val` 按 ST_OnOff 解析；
5. 图片只认 run 内 `a:blip/@r:embed`，经 `word/_rels/document.xml.rels` 取 `word/media/*`；
6. `row.cells` 复刻 `gridSpan` 展开与 `vMerge=continue` 的「按网格偏移向上寻根」；
7. `p.style.name` 复刻 python-docx 的内置样式显示名转换：真实报告里 `w:name` 是小写
   `heading 1/2/3`，python-docx 返回 `Heading 1/2/3`。**不做这步，
   `is_report_docx` 的 `startswith("Heading")` 会失败，整份报告会被误判成固定模板。**

安全：解析器以 `resolve_entities=False` / `no_network=True` / `load_dtd=False` 构造，
与 python-docx 的 oxml 解析器一致（XXE 结论不变，见 `docx_parser` 文件头）。
"""
import posixpath
from zipfile import ZipFile

from lxml import etree

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _t(namespace: str, local: str) -> str:
    return f"{{{namespace}}}{local}"


_W_BODY = _t(_W, "body")
_W_P = _t(_W, "p")
_W_TBL = _t(_W, "tbl")
_W_TR = _t(_W, "tr")
_W_TC = _t(_W, "tc")
_W_R = _t(_W, "r")
_W_T = _t(_W, "t")
_W_TAB = _t(_W, "tab")
_W_PTAB = _t(_W, "ptab")
_W_BR = _t(_W, "br")
_W_CR = _t(_W, "cr")
_W_NO_BREAK_HYPHEN = _t(_W, "noBreakHyphen")
_W_RPR = _t(_W, "rPr")
_W_B = _t(_W, "b")
_W_I = _t(_W, "i")
_W_PPR = _t(_W, "pPr")
_W_PSTYLE = _t(_W, "pStyle")
_W_TCPR = _t(_W, "tcPr")
_W_TRPR = _t(_W, "trPr")
_W_GRID_SPAN = _t(_W, "gridSpan")
_W_GRID_BEFORE = _t(_W, "gridBefore")
_W_VMERGE = _t(_W, "vMerge")
_W_HYPERLINK = _t(_W, "hyperlink")
_W_STYLE = _t(_W, "style")
_W_NAME = _t(_W, "name")
_W_VAL = _t(_W, "val")
_W_TYPE = _t(_W, "type")
_W_DEFAULT = _t(_W, "default")
_A_BLIP = _t(_A, "blip")
_R_EMBED = _t(_R, "embed")
_PKG_RELATIONSHIP = _t(_PKG_REL, "Relationship")
_FALSE_ON_OFF = {"0", "false", "off"}

# 与 `docx.styles.BabelFish.style_aliases` 一致（python-docx 1.2）；
# 直接复刻而非 import，避免 reader 依赖 python-docx 内部实现。
_STYLE_ALIASES = {"caption": "Caption", "footer": "Footer", "header": "Header"}
_STYLE_ALIASES.update({f"heading {n}": f"Heading {n}" for n in range(1, 10)})


class _Blip:
    """`a:blip` 的最小替身：`_save_image` 只用到 `blip.get(r:embed)`。"""

    __slots__ = ("_rid",)

    def __init__(self, rid: str):
        self._rid = rid

    def get(self, key):
        return self._rid if key == _R_EMBED else None


class _RunElement:
    """`run._element` 的替身：只暴露 `.iter(a:blip)`（`_run_to_html` 的唯一用法）。"""

    __slots__ = ("_blips",)

    def __init__(self, rids: tuple[str, ...]):
        self._blips = tuple(_Blip(rid) for rid in rids)

    def iter(self, tag):
        return iter(self._blips) if tag == _A_BLIP else iter(())


class Run:
    __slots__ = ("text", "bold", "italic", "_element")

    def __init__(self, text: str, bold: bool | None, italic: bool | None, rids: tuple[str, ...]):
        self.text = text
        self.bold = bold
        self.italic = italic
        self._element = _RunElement(rids)


class Paragraph:
    __slots__ = ("text", "runs", "style")

    def __init__(self, text: str, runs: list[Run], style_name: str | None):
        self.text = text
        self.runs = runs
        self.style = _Style(style_name)


class _Style:
    __slots__ = ("name",)

    def __init__(self, name: str | None):
        self.name = name


class Cell:
    __slots__ = ("paragraphs", "text")

    def __init__(self, paragraphs: list[Paragraph]):
        self.paragraphs = paragraphs
        self.text = "\n".join(p.text for p in paragraphs)


class Row:
    __slots__ = ("cells",)

    def __init__(self, cells: list[Cell]):
        self.cells = tuple(cells)


class Table:
    __slots__ = ("rows",)

    def __init__(self, rows: list[Row]):
        self.rows = tuple(rows)


class _ImagePart:
    __slots__ = ("partname", "blob")

    def __init__(self, partname: str, blob: bytes):
        self.partname = partname
        self.blob = blob


class _Part:
    __slots__ = ("related_parts",)

    def __init__(self, related_parts: dict[str, _ImagePart]):
        self.related_parts = related_parts


class Document:
    """只读文档门面（构造参数与 python-docx `Document(path)` 对齐）。"""

    __slots__ = ("paragraphs", "tables", "part")

    def __init__(self, path: str | bytes):
        with ZipFile(path) as archive:
            styles = _load_styles(archive)
            self.paragraphs, self.tables = _load_body(archive, styles)
            self.part = _Part(_load_related_parts(archive))


# --------------------------------------------------------------------------- 解析


def _xml_parser() -> etree.XMLParser:
    # 与 python-docx 的 oxml 解析器口径一致：不解析实体、不联网、不加载 DTD。
    return etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False
    )


# `etree.iterparse` 不吃 XMLParser 实例，只接受同名的安全开关。
_SAFE_ITERPARSE = {
    "resolve_entities": False,
    "no_network": True,
    "load_dtd": False,
    "huge_tree": False,
    "remove_blank_text": False,
}


def _load_styles(archive: ZipFile) -> tuple[dict[str, str], str | None]:
    try:
        root = etree.fromstring(archive.read("word/styles.xml"), parser=_xml_parser())
    except KeyError:
        return {}, None
    names: dict[str, str] = {}
    default_name: str | None = None
    for style in root.iter(_W_STYLE):
        if style.get(_W_TYPE) != "paragraph":
            continue
        name_el = style.find(_W_NAME)
        if name_el is None:
            continue
        name = name_el.get(_W_VAL)
        style_id = style.get(_t(_W, "styleId"))
        if style_id:
            names[style_id] = name
        if style.get(_W_DEFAULT) == "1":
            default_name = name
    return names, default_name


def _style_display_name(styles, style_id: str | None) -> str | None:
    names, default_name = styles
    raw = names.get(style_id) if style_id else None
    if raw is None:
        raw = default_name
    if raw is None:
        return None
    return _STYLE_ALIASES.get(raw, raw)


def _on_off(rpr, tag: str) -> bool | None:
    if rpr is None:
        return None
    element = rpr.find(tag)
    if element is None:
        return None
    value = element.get(_W_VAL)
    if value is None:
        return True
    return value.strip().lower() not in _FALSE_ON_OFF


def _run_text(element) -> str:
    pieces: list[str] = []
    for child in element:
        tag = child.tag
        if tag == _W_T:
            pieces.append(child.text or "")
        elif tag == _W_TAB or tag == _W_PTAB:
            pieces.append("\t")
        elif tag == _W_CR:
            pieces.append("\n")
        elif tag == _W_NO_BREAK_HYPHEN:
            pieces.append("-")
        elif tag == _W_BR:
            pieces.append("\n" if child.get(_W_TYPE, "textWrapping") == "textWrapping" else "")
    return "".join(pieces)


def _make_run(element) -> Run:
    rpr = element.find(_W_RPR)
    rids = tuple(
        rid for rid in (blip.get(_R_EMBED) for blip in element.iter(_A_BLIP)) if rid
    )
    return Run(
        _run_text(element),
        _on_off(rpr, _W_B),
        _on_off(rpr, _W_I),
        rids,
    )


def _make_paragraph(element, styles) -> Paragraph:
    ppr = element.find(_W_PPR)
    style_id = None
    if ppr is not None:
        pstyle = ppr.find(_W_PSTYLE)
        if pstyle is not None:
            style_id = pstyle.get(_W_VAL)
    runs = [_make_run(r) for r in element.findall(_W_R)]
    # `p.text` 走 `w:r | w:hyperlink`（含超链接可见文字），`p.runs` 只含直接 `w:r`。
    parts: list[str] = []
    for child in element:
        if child.tag == _W_R:
            parts.append(_run_text(child))
        elif child.tag == _W_HYPERLINK:
            parts.extend(_run_text(r) for r in child.findall(_W_R))
    return Paragraph("".join(parts), runs, _style_display_name(styles, style_id))


def _make_cell(element, styles) -> Cell:
    return Cell([_make_paragraph(p, styles) for p in element.findall(_W_P)])


def _grid_span(tc) -> int:
    tcpr = tc.find(_W_TCPR)
    if tcpr is None:
        return 1
    span = tcpr.find(_W_GRID_SPAN)
    if span is None:
        return 1
    try:
        return int(span.get(_W_VAL) or 1)
    except ValueError:
        return 1


def _row_grid_before(tr) -> int:
    trpr = tr.find(_W_TRPR)
    if trpr is None:
        return 0
    before = trpr.find(_W_GRID_BEFORE)
    if before is None:
        return 0
    try:
        return int(before.get(_W_VAL) or 0)
    except ValueError:
        return 0


def _vmerge(tc) -> str | None:
    tcpr = tc.find(_W_TCPR)
    if tcpr is None:
        return None
    vmerge = tcpr.find(_W_VMERGE)
    if vmerge is None:
        return None
    return vmerge.get(_W_VAL) or "continue"


def _make_table(element, styles) -> Table:
    raw_rows: list[list[tuple]] = []
    for tr in element.findall(_W_TR):
        offset = _row_grid_before(tr)
        cells = []
        for tc in tr.findall(_W_TC):
            span = _grid_span(tc)
            cells.append((tc, offset, span))
            offset += span
        raw_rows.append(cells)

    resolved: dict[tuple[int, int], tuple[Cell, int]] = {}

    def find_tc(row_index: int, offset: int):
        if row_index < 0:
            return None
        for tc, tc_offset, span in raw_rows[row_index]:
            if tc_offset == offset:
                return tc, span
        return None

    def resolve(row_index: int, offset: int) -> tuple[Cell, int] | None:
        key = (row_index, offset)
        if key in resolved:
            return resolved[key]
        found = find_tc(row_index, offset)
        if found is None:
            return None
        tc, span = found
        if _vmerge(tc) == "continue":
            above = resolve(row_index - 1, offset)
            if above is None:
                return None
            resolved[key] = above
            return above
        cell = _make_cell(tc, styles)
        resolved[key] = (cell, span)
        return cell, span

    rows: list[Row] = []
    for row_index, raw_cells in enumerate(raw_rows):
        cells: list[Cell] = []
        for _tc, offset, _span in raw_cells:
            root = resolve(row_index, offset)
            if root is None:
                continue
            cell, root_span = root
            cells.extend(cell for _ in range(root_span))
        rows.append(Row(cells))
    return Table(rows)


def _clear(element) -> None:
    element.clear()
    while element.getprevious() is not None:
        del element.getparent()[0]


def _load_body(archive: ZipFile, styles) -> tuple[list[Paragraph], list[Table]]:
    paragraphs: list[Paragraph] = []
    tables: list[Table] = []
    with archive.open("word/document.xml") as stream:
        context = etree.iterparse(stream, events=("end",), **_SAFE_ITERPARSE)
        for _event, element in context:
            if element.tag == _W_BODY:
                break
            parent = element.getparent()
            if parent is None or parent.tag != _W_BODY:
                continue
            if element.tag == _W_P:
                paragraphs.append(_make_paragraph(element, styles))
                _clear(element)
            elif element.tag == _W_TBL:
                tables.append(_make_table(element, styles))
                _clear(element)
    return paragraphs, tables


def _load_related_parts(archive: ZipFile) -> dict[str, _ImagePart]:
    try:
        root = etree.fromstring(
            archive.read("word/_rels/document.xml.rels"), parser=_xml_parser()
        )
    except KeyError:
        return {}
    parts: dict[str, _ImagePart] = {}
    for rel in root.iter(_PKG_RELATIONSHIP):
        rid = rel.get("Id")
        target = rel.get("Target")
        if not rid or not target or rel.get("TargetMode") == "External":
            continue
        partname = target if target.startswith("/") else posixpath.normpath(f"word/{target}")
        try:
            blob = archive.read(partname.lstrip("/"))
        except KeyError:
            continue
        parts[rid] = _ImagePart(partname, blob)
    return parts
