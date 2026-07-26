"""报告 Word 构建：封面 + 漏洞汇总表 + 富文本章节（htmldocx 转换）。"""
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor
from htmldocx import HtmlToDocx

from app.constants import VUL_LEVEL, VUL_STATUS, VUL_TYPE
from app.core.config import settings

_STORAGE_SRC = re.compile(r'src="/storage/([^"]+)"')


def _localize_images(html: str) -> str:
    """把 /storage/xx 图片 URL 替换为本地文件路径，供 htmldocx 内嵌图片。"""

    def repl(m: re.Match) -> str:
        local = settings.storage_path / m.group(1)
        return f'src="{local.as_posix()}"'

    return _STORAGE_SRC.sub(repl, html or "")


def _add_html(doc: Document, html: str) -> None:
    html = _localize_images(html)
    if not html.strip():
        return
    parser = HtmlToDocx()
    try:
        parser.add_html_to_document(html, doc)
    except Exception:
        # 富文本转换失败时降级为纯文本，避免导出整体失败
        text = re.sub(r"<[^>]+>", "", html)
        doc.add_paragraph(text)


def _cover(doc: Document, meta: dict) -> None:
    for _ in range(4):
        doc.add_paragraph()
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run(meta.get("title") or "安全测试报告")
    run.font.size = Pt(32)
    run.font.bold = True
    run.font.color.rgb = RGBColor(0x1F, 0x3A, 0x63)

    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run(meta.get("project_name", "")).font.size = Pt(16)

    doc.add_paragraph()
    info = doc.add_table(rows=4, cols=2)
    info.style = "Table Grid"
    items = [
        ("委托单位", meta.get("customer", "")),
        ("报告作者", meta.get("author", "")),
        ("测试周期", f"{meta.get('test_start', '')} ~ {meta.get('test_end', '')}"),
        ("报告状态", "正式版" if meta.get("status") == "final" else "草稿"),
    ]
    for i, (k, v) in enumerate(items):
        info.rows[i].cells[0].text = k
        info.rows[i].cells[1].text = v
    doc.add_page_break()


def _summary_table(doc: Document, vulns: list[dict]) -> None:
    doc.add_heading("漏洞汇总", level=1)
    if not vulns:
        doc.add_paragraph("本次报告未关联漏洞记录。")
        return
    table = doc.add_table(rows=len(vulns) + 1, cols=5)
    table.style = "Table Grid"
    headers = ["序号", "漏洞名称", "类型", "等级", "状态"]
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        cell.paragraphs[0].runs[0].font.bold = True
    for idx, v in enumerate(vulns, start=1):
        row = table.rows[idx]
        row.cells[0].text = str(idx)
        row.cells[1].text = v.get("title", "")
        row.cells[2].text = VUL_TYPE.get(v.get("vul_type"), "其他")
        row.cells[3].text = VUL_LEVEL.get(v.get("level"), "-")
        row.cells[4].text = VUL_STATUS.get(v.get("status"), "-")


def build_report_docx(meta: dict, vulns: list[dict], sections: list[dict], out_path: str) -> str:
    """生成报告 docx。

    meta: 报告元信息；vulns: 汇总表数据；sections: [{title, content_html}] 有序章节。
    """
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    _cover(doc, meta)

    if meta.get("summary_html"):
        doc.add_heading("测试结论", level=1)
        _add_html(doc, meta["summary_html"])

    _summary_table(doc, vulns)
    doc.add_page_break()

    doc.add_heading("漏洞详情", level=1)
    for i, section in enumerate(sections, start=1):
        doc.add_heading(f"{i}. {section.get('title') or '未命名章节'}", level=2)
        _add_html(doc, section.get("content_html", ""))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return out_path
