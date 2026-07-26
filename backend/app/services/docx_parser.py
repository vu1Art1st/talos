"""Word 固定模板解析：每个漏洞为一张两列信息表格。

模板规范（/api/v1/imports/template 可下载示例）：
- 表格第一列为字段标签：漏洞名称 / 漏洞等级 / 漏洞类型 / 影响URL / 漏洞描述 / 复现步骤 / 修复建议
- 第二列为内容，描述/复现/建议单元格支持多段落与截图
- 文档中可包含任意数量的漏洞表格，其余段落内容会被忽略
"""
import html as html_mod
import re
import uuid
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import _Cell

from app.constants import IMPORT_LABEL_MAP, VUL_LEVEL_REVERSE, VUL_TYPE_REVERSE

_A_BLIP = qn("a:blip")
_R_EMBED = qn("r:embed")


def _norm_label(text: str) -> str:
    return re.sub(r"[\s:：]+", "", text or "")


def _save_image(part, rid: str, image_dir: Path, url_prefix: str) -> str | None:
    """把 run 中引用的图片落盘，返回可访问 URL。"""
    try:
        image_part = part.related_parts[rid]
    except KeyError:
        return None
    ext = Path(str(image_part.partname)).suffix or ".png"
    name = f"{uuid.uuid4().hex}{ext}"
    image_dir.mkdir(parents=True, exist_ok=True)
    (image_dir / name).write_bytes(image_part.blob)
    return f"{url_prefix}/{name}"


def _run_to_html(run, part, image_dir: Path, url_prefix: str) -> str:
    pieces: list[str] = []
    # 图片：w:drawing 内的 a:blip r:embed 引用
    for blip in run._element.iter(_A_BLIP):
        rid = blip.get(_R_EMBED)
        if rid:
            url = _save_image(part, rid, image_dir, url_prefix)
            if url:
                pieces.append(f'<img src="{url}">')
    text = html_mod.escape(run.text or "")
    if text:
        if run.bold:
            text = f"<strong>{text}</strong>"
        if run.italic:
            text = f"<em>{text}</em>"
        pieces.append(text)
    return "".join(pieces)


def _cell_to_html(cell: _Cell, part, image_dir: Path, url_prefix: str) -> str:
    paragraphs: list[str] = []
    for p in cell.paragraphs:
        inner = "".join(_run_to_html(r, part, image_dir, url_prefix) for r in p.runs)
        if inner.strip():
            paragraphs.append(f"<p>{inner}</p>")
    return "".join(paragraphs)


def _cell_text(cell: _Cell) -> str:
    return "\n".join(p.text for p in cell.paragraphs).strip()


def _map_level(text: str) -> int | None:
    text = _norm_label(text)
    if text in VUL_LEVEL_REVERSE:
        return VUL_LEVEL_REVERSE[text]
    for name, code in VUL_LEVEL_REVERSE.items():
        if text and (text in name or name in text):
            return code
    return None


def _map_type(text: str) -> int | None:
    text = _norm_label(text)
    if text in VUL_TYPE_REVERSE:
        return VUL_TYPE_REVERSE[text]
    for name, code in VUL_TYPE_REVERSE.items():
        if text and (text in name or name in text):
            return code
    return None


def parse_docx(file_path: str, image_dir: str, image_url_prefix: str) -> list[dict]:
    """解析文档，返回记录列表。单条记录解析失败不影响整批。

    每条记录: {title, level, vul_type, affected_url,
               description_html, reproduce_html, solution_html, errors: [str]}
    """
    doc = Document(file_path)
    part = doc.part
    img_dir = Path(image_dir)
    results: list[dict] = []

    for table in doc.tables:
        fields: dict[str, _Cell] = {}
        for row in table.rows:
            if len(row.cells) < 2:
                continue
            label = _norm_label(_cell_text(row.cells[0]))
            key = IMPORT_LABEL_MAP.get(label)
            if key and key not in fields:
                fields[key] = row.cells[1]

        if "title" not in fields:
            continue  # 非漏洞信息表格，跳过

        record: dict = {
            "title": _cell_text(fields["title"]),
            "level": 30,
            "vul_type": 75,
            "affected_url": "",
            "description_html": "",
            "reproduce_html": "",
            "solution_html": "",
            "errors": [],
        }
        if not record["title"]:
            record["errors"].append("漏洞名称为空")

        if "level" in fields:
            level = _map_level(_cell_text(fields["level"]))
            if level is None:
                record["errors"].append(f"无法识别漏洞等级「{_cell_text(fields['level'])}」，已按中危处理")
            else:
                record["level"] = level
        else:
            record["errors"].append("缺少「漏洞等级」行，已按中危处理")

        if "vul_type" in fields:
            vtype = _map_type(_cell_text(fields["vul_type"]))
            if vtype is None:
                record["errors"].append(f"无法识别漏洞类型「{_cell_text(fields['vul_type'])}」，已按其他处理")
            else:
                record["vul_type"] = vtype

        if "affected_url" in fields:
            record["affected_url"] = _cell_text(fields["affected_url"])[:512]

        for key in ("description_html", "reproduce_html", "solution_html"):
            if key in fields:
                record[key] = _cell_to_html(fields[key], part, img_dir, image_url_prefix)

        results.append(record)

    return results


def build_import_template() -> Document:
    """生成标准导入模板文档（含填写示例）。"""
    doc = Document()
    doc.add_heading("漏洞导入模板", level=0)
    doc.add_paragraph("填写说明：每个漏洞使用一张下方格式的表格，可复制多份；"
                      "表格以外的内容不会被导入。漏洞等级取值：严重/高危/中危/低危。")

    rows = [
        ("漏洞名称", "示例：后台登录接口存在SQL注入"),
        ("漏洞等级", "高危"),
        ("漏洞类型", "SQL注入漏洞"),
        ("影响URL", "https://example.com/api/login"),
        ("漏洞描述", "在此填写漏洞描述，可包含多段文字与截图。"),
        ("复现步骤", "1. 打开登录页\n2. 在用户名输入 ' or 1=1--\n3. 观察返回"),
        ("修复建议", "使用参数化查询，过滤特殊字符。"),
    ]
    table = doc.add_table(rows=len(rows), cols=2)
    table.style = "Table Grid"
    for i, (label, value) in enumerate(rows):
        table.rows[i].cells[0].text = label
        table.rows[i].cells[1].text = value
    return doc
