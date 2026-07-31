"""report_builder 与报告 HTML 助手的纯函数单元测试（不依赖数据库 / 队列）。

覆盖计划测试项：
- 汇总统计仅计入未修复漏洞、已修复状态单元格绿色
- 详情「测试状态：」按漏洞最新 is_retest 重写
- settings 中 w:updateFields 位于 w:hdrShapeDefaults 之前
- 封面第二行为 project_name（系统名称）
- _affected_urls_html / _vuln_section_html 多 URL 渲染
"""
from docx import Document
from docx.oxml.ns import qn

from app.api.v1.reports import _affected_urls_html, _vuln_section_html
from app.constants import VulStatus
from app.services.report_builder import FIXED_STATUS_COLOR, build_report_docx


def _build(tmp_path, meta=None, vulns=None, sections=None):
    meta = {"title": "报告标题", "project_name": "统一门户系统", **(meta or {})}
    out = str(tmp_path / "out.docx")
    build_report_docx(meta, vulns or [], sections or [], out)
    return Document(out)


def _cell_run_colors(cell):
    return [run.font.color.rgb for p in cell.paragraphs for run in p.runs]


def test_affected_urls_html_multi_value():
    # 多 URL 以换行分隔存储，逐条转义后以 <br/> 连接
    html = _affected_urls_html("https://a.com/x\nhttps://b.com/y?a=1&b=2\n")
    assert html == "https://a.com/x<br/>https://b.com/y?a=1&amp;b=2"
    # 空值回退占位符
    assert _affected_urls_html("") == "-"
    assert _affected_urls_html(None) == "-"


def test_vuln_section_html_multi_url():
    class _V:
        is_retest = False
        level = 20
        affected_url = "https://a.com/1\nhttps://a.com/2"
        description_html = ""
        reproduce_html = ""
        solution_html = ""
        retest_html = ""

    html = _vuln_section_html(_V())
    assert "漏洞链接：</strong>https://a.com/1<br/>https://a.com/2" in html


def test_summary_counts_exclude_fixed_and_green_cell(tmp_path):
    vulns = [
        {"id": 1, "title": "高危未修复", "level": 20, "vul_type": 10,
         "status": VulStatus.UNFIXED, "is_retest": False},
        {"id": 2, "title": "高危已修复", "level": 20, "vul_type": 10,
         "status": VulStatus.FIXED, "is_retest": False},
    ]
    doc = _build(tmp_path, vulns=vulns)

    # 统计段：高危漏洞仅计未修复 = 1 个
    para_texts = [p.text.strip() for p in doc.paragraphs]
    assert any(t.startswith("高危漏洞1个") for t in para_texts), para_texts

    # 汇总表列出全部漏洞（表头 + 2 行）
    table = doc.tables[6]
    assert len(table.rows) == 3
    # 已修复行状态列为绿色，未修复行状态列非绿色
    fixed_row = next(r for r in table.rows[1:] if r.cells[2].text.strip() == "高危已修复")
    unfixed_row = next(r for r in table.rows[1:] if r.cells[2].text.strip() == "高危未修复")
    assert FIXED_STATUS_COLOR in _cell_run_colors(fixed_row.cells[3])
    assert FIXED_STATUS_COLOR not in _cell_run_colors(unfixed_row.cells[3])


def test_detail_test_state_rewritten_by_is_retest(tmp_path):
    # 章节快照写「初测」，但漏洞已复测，导出应改写为「复测」
    vulns = [{"id": 1, "title": "复测漏洞", "level": 20, "vul_type": 10,
              "status": VulStatus.FIXING, "is_retest": True}]
    sections = [{"title": "复测漏洞", "vul_id": 1,
                 "content_html": "<p><strong>测试状态：</strong>初测</p>"}]
    doc = _build(tmp_path, vulns=vulns, sections=sections)
    body = [p.text for p in doc.paragraphs]
    assert any("测试状态：复测" in t for t in body), body
    # 修复中 + 复测 = 复测未通过（标题后缀）
    h3 = [p.text for p in doc.paragraphs if p.style.name == "Heading 3"]
    assert any(t.endswith("（复测未通过）") for t in h3), h3


def test_cover_second_line_is_project_name(tmp_path):
    doc = _build(tmp_path, meta={"project_name": "网上营业厅"})
    texts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    assert "网上营业厅" in texts


def test_update_fields_precedes_compat_anchor(tmp_path):
    doc = _build(tmp_path)
    settings_el = doc.settings.element
    children = list(settings_el)
    update = settings_el.find(qn("w:updateFields"))
    assert update is not None
    # updateFields 必须排在 hdrShapeDefaults / compat / rsids 等锚点之前
    anchor_tags = {qn(t) for t in (
        "w:hdrShapeDefaults", "w:footnotePr", "w:endnotePr",
        "w:compat", "w:rsids", "m:mathPr", "w:themeFontLang",
    )}
    anchors = [i for i, c in enumerate(children) if c.tag in anchor_tags]
    if anchors:
        assert children.index(update) < min(anchors)
