"""docx_parser 固定模板解析单元测试。"""
import base64
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.shared import Inches

from app.services.docx_parser import build_import_template, parse_docx

# 1x1 红色 PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _make_docx(path: Path, with_image: bool = True) -> None:
    doc = Document()
    doc.add_heading("渗透测试结果", level=1)
    doc.add_paragraph("以下为本次测试发现的漏洞。")

    rows = [
        ("漏洞名称", "登录接口存在SQL注入"),
        ("漏洞等级", "高危"),
        ("漏洞类型", "SQL注入"),
        ("影响URL", "https://example.com/api/login"),
        ("漏洞描述", "登录接口 username 参数未过滤。"),
        ("复现步骤", "输入 ' or 1=1-- 后返回全部数据。"),
        ("修复建议", "使用参数化查询。"),
    ]
    table = doc.add_table(rows=len(rows), cols=2)
    for i, (label, value) in enumerate(rows):
        table.rows[i].cells[0].text = label
        table.rows[i].cells[1].text = value

    if with_image:
        cell = table.rows[5].cells[1]  # 复现步骤单元格追加截图
        run = cell.add_paragraph().add_run()
        run.add_picture(BytesIO(_PNG), width=Inches(0.2))

    # 干扰表格：无「漏洞名称」行，应被跳过
    other = doc.add_table(rows=1, cols=2)
    other.rows[0].cells[0].text = "备注"
    other.rows[0].cells[1].text = "非漏洞表格"

    doc.save(str(path))


def test_parse_docx_basic(tmp_path: Path):
    docx_file = tmp_path / "sample.docx"
    _make_docx(docx_file)
    image_dir = tmp_path / "images"

    records = parse_docx(str(docx_file), str(image_dir), "/storage/uploads/test")

    assert len(records) == 1
    rec = records[0]
    assert rec["title"] == "登录接口存在SQL注入"
    assert rec["level"] == 20  # 高危
    assert rec["affected_url"] == "https://example.com/api/login"
    assert "username 参数未过滤" in rec["description_html"]
    assert "参数化查询" in rec["solution_html"]
    assert rec["errors"] == []

    # 图片被提取落盘并替换为 <img> 引用
    assert '<img src="/storage/uploads/test/' in rec["reproduce_html"]
    saved = list(image_dir.glob("*"))
    assert len(saved) == 1
    assert saved[0].read_bytes() == _PNG


def test_parse_docx_unknown_level(tmp_path: Path):
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "漏洞名称"
    table.rows[0].cells[1].text = "弱口令"
    table.rows[1].cells[0].text = "漏洞等级"
    table.rows[1].cells[1].text = "未知等级"
    docx_file = tmp_path / "bad_level.docx"
    doc.save(str(docx_file))

    records = parse_docx(str(docx_file), str(tmp_path / "img"), "/x")
    assert len(records) == 1
    assert records[0]["level"] == 30  # 回落中危
    assert any("无法识别漏洞等级" in e for e in records[0]["errors"])


def test_parse_docx_no_table(tmp_path: Path):
    doc = Document()
    doc.add_paragraph("这是一篇没有表格的文档。")
    docx_file = tmp_path / "empty.docx"
    doc.save(str(docx_file))

    assert parse_docx(str(docx_file), str(tmp_path / "img"), "/x") == []


def test_import_template_roundtrip(tmp_path: Path):
    """官方模板应能被解析器识别。"""
    docx_file = tmp_path / "template.docx"
    build_import_template().save(str(docx_file))

    records = parse_docx(str(docx_file), str(tmp_path / "img"), "/x")
    assert len(records) == 1
    assert records[0]["level"] == 20  # 模板示例为高危
    assert records[0]["errors"] == []
