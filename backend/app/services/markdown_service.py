"""远程漏洞 Markdown → 富文本转换。

安全边界：
- Markdown 原始 HTML 关闭，`<script>` 等内容只会作为文本显示；
- 渲染后的 HTML 统一经过 `core.sanitize.sanitize_html`；
- 图片只允许引用本系统 `/storage/uploads/images/<32位hex>.<ext>`；
- 转换结果同时生成 HTML 与 ProseMirror JSON，供站内 TipTap 编辑器直接消费。
"""
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString, Tag
from fastapi import HTTPException
from markdown_it import MarkdownIt

from app.core.sanitize import sanitize_html

CONVERTER_VERSION = "markdown-v1"

_MARKDOWN = MarkdownIt(
    "commonmark",
    {"html": False, "linkify": False, "typographer": False, "breaks": False},
).enable(["table", "strikethrough"])

_IMAGE_SRC_RE = re.compile(
    r"^/storage/uploads/images/[0-9a-f]{32}\.(?:png|jpe?g|gif|webp)$",
)
_IMAGE_NAME_RE = re.compile(
    r"^/storage/uploads/images/([0-9a-f]{32}\.(?:png|jpe?g|gif|webp))$",
)


@dataclass(frozen=True)
class RenderedMarkdown:
    html: str
    json: dict
    image_names: tuple[str, ...]


def render_markdown(source: str, *, field_name: str = "Markdown") -> RenderedMarkdown:
    """渲染并校验一段漏洞正文 Markdown。"""
    html = sanitize_html(_MARKDOWN.render(source))
    soup = BeautifulSoup(html, "html.parser")
    image_names = _validate_images(soup)
    _validate_links(soup)
    if not _has_visible_content(soup):
        raise HTTPException(422, f"{field_name} 清洗后不能为空")
    return RenderedMarkdown(
        html=html,
        json={"type": "doc", "content": _block_nodes(soup)},
        image_names=image_names,
    )


def _validate_images(soup: BeautifulSoup) -> tuple[str, ...]:
    names: list[str] = []
    for image in soup.find_all("img"):
        src = str(image.get("src") or "").strip()
        if not _IMAGE_SRC_RE.match(src):
            raise HTTPException(
                422,
                "Markdown 图片必须使用本系统上传接口返回的 "
                "/storage/uploads/images/<文件名> 路径",
            )
        match = _IMAGE_NAME_RE.match(src)
        if match:
            names.append(match.group(1))
    return tuple(dict.fromkeys(names))


def _validate_links(soup: BeautifulSoup) -> None:
    for link in soup.find_all("a"):
        href = str(link.get("href") or "").strip()
        if href and not href.startswith(("http://", "https://")):
            raise HTTPException(422, "Markdown 链接只允许 http/https 地址")


def _has_visible_content(soup: BeautifulSoup) -> bool:
    return bool(soup.get_text(strip=True) or soup.find("img"))


def _block_nodes(container: Tag | BeautifulSoup) -> list[dict]:
    nodes: list[dict] = []
    for child in container.children:
        node = _block_node(child)
        if node is not None:
            nodes.append(node)
    return nodes


def _block_node(node: Tag | NavigableString) -> dict | None:
    if isinstance(node, NavigableString):
        text = str(node)
        if not text.strip():
            return None
        return _paragraph(_inline_text(text))
    if not isinstance(node, Tag):
        return None

    name = node.name.lower()
    if name == "p":
        content = _inline_nodes(node)
        return _paragraph(content) if content else None
    if name in {"h1", "h2", "h3", "h4"}:
        content = _inline_nodes(node, marks=[{"type": "bold"}])
        return _paragraph(content) if content else None
    if name in {"ul", "ol"}:
        return _list_node(node, ordered=name == "ol")
    if name == "blockquote":
        content = _block_nodes(node)
        return {"type": "blockquote", "content": content} if content else None
    if name == "pre":
        code = node.find("code")
        text = (code or node).get_text()
        if not text.strip():
            return None
        return {"type": "codeBlock", "content": [{"type": "text", "text": text}]}
    if name == "table":
        return _table_node(node)
    if name in {"thead", "tbody", "tr", "td", "th"}:
        return None
    if name in {"br", "hr"}:
        return None
    content = _inline_nodes(node)
    return _paragraph(content) if content else None


def _paragraph(content: list[dict]) -> dict:
    return {"type": "paragraph", "content": content}


def _inline_text(text: str, marks: list[dict] | None = None) -> list[dict]:
    if not text:
        return []
    node = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return [node]


def _inline_nodes(node: Tag, marks: list[dict] | None = None) -> list[dict]:
    marks = marks or []
    nodes: list[dict] = []
    for child in node.children:
        if isinstance(child, NavigableString):
            nodes.extend(_inline_text(str(child), marks))
            continue
        if not isinstance(child, Tag):
            continue

        name = child.name.lower()
        if name == "br":
            nodes.append({"type": "hardBreak"})
        elif name == "img":
            src = str(child.get("src") or "").strip()
            nodes.append({
                "type": "image",
                "attrs": {
                    "src": src,
                    "alt": str(child.get("alt") or ""),
                    "title": str(child.get("title") or ""),
                },
            })
        elif name in {"strong", "b"}:
            nodes.extend(_inline_nodes(child, _merge_mark(marks, "bold")))
        elif name in {"em", "i"}:
            nodes.extend(_inline_nodes(child, _merge_mark(marks, "italic")))
        elif name in {"s", "strike", "del"}:
            nodes.extend(_inline_nodes(child, _merge_mark(marks, "strike")))
        elif name == "code":
            nodes.extend(_inline_nodes(child, _merge_mark(marks, "code")))
        elif name == "a":
            href = str(child.get("href") or "").strip()
            link_marks = _merge_mark(
                marks, "link", {"href": href, "target": "_blank", "rel": "noopener noreferrer"},
            )
            nodes.extend(_inline_nodes(child, link_marks))
        else:
            nodes.extend(_inline_nodes(child, marks))
    return [node for node in nodes if node.get("type") != "text" or node.get("text")]


def _merge_mark(marks: list[dict], mark_type: str, attrs: dict | None = None) -> list[dict]:
    merged = [dict(mark) for mark in marks]
    mark = {"type": mark_type}
    if attrs:
        mark["attrs"] = attrs
    merged.append(mark)
    return merged


def _list_node(node: Tag, *, ordered: bool) -> dict:
    items = [
        _list_item_node(child)
        for child in node.find_all("li", recursive=False)
    ]
    result = {
        "type": "orderedList" if ordered else "bulletList",
        "content": [item for item in items if item is not None],
    }
    if ordered:
        start = node.get("start")
        if start and str(start).isdigit() and int(start) != 1:
            result["attrs"] = {"start": int(start)}
    return result


def _list_item_node(node: Tag) -> dict | None:
    content = _block_nodes(node)
    if not content:
        return None
    return {"type": "listItem", "content": content}


def _table_node(node: Tag) -> dict | None:
    rows: list[dict] = []
    for row in node.find_all("tr"):
        cells: list[dict] = []
        for cell in row.find_all(["th", "td"], recursive=False):
            attrs: dict = {}
            if cell.get("colspan"):
                attrs["colspan"] = int(cell["colspan"])
            if cell.get("rowspan"):
                attrs["rowspan"] = int(cell["rowspan"])
            content = _block_nodes(cell) or [_paragraph([])]
            cell_node = {
                "type": "tableHeader" if cell.name.lower() == "th" else "tableCell",
                "content": content,
            }
            if attrs:
                cell_node["attrs"] = attrs
            cells.append(cell_node)
        if cells:
            rows.append({"type": "tableRow", "content": cells})
    return {"type": "table", "content": rows} if rows else None
