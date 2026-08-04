"""报告 Word 构建：以渗透测试报告模板为基底，填充封面 / 版本记录 / 测试目标 / 汇总统计 / 漏洞详情。

模板锚点依赖 backend/app/templates/report_template.docx 的固定结构：
表0 封面装饰 | 表1 版本变更记录 | 表2 适用性声明 | 表3 目录(TOC 域)
表4 测试目标 | 表5 时间与人员 | 表6 风险问题汇总
"""
import copy
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, RGBColor
from docx.table import Table, _Row
from docx.text.paragraph import Paragraph
from htmldocx import HtmlToDocx

from app.constants import VUL_LEVEL_EXPORT, VUL_STATUS, VUL_TYPE, VulStatus
from app.core.config import settings

_STORAGE_SRC = re.compile(r'src="/storage/([^"]+)"')
_HEADING_OPEN = re.compile(r"<h[1-6][^>]*>", re.IGNORECASE)
_HEADING_CLOSE = re.compile(r"</h[1-6]>", re.IGNORECASE)
# 章节快照中「测试状态：」后的初测/复测标记，导出时按漏洞最新 is_retest 重写
_TEST_STATE = re.compile(r"(测试状态：</strong>)\s*(?:初测|复测)")

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


def _add_html(doc: Document, html: str) -> None:
    html = _localize_images(_demote_headings(html))
    if not html.strip():
        return
    parser = HtmlToDocx()
    try:
        parser.add_html_to_document(html, doc)
    except Exception:
        # 富文本转换失败时降级为纯文本，避免导出整体失败
        text = re.sub(r"<[^>]+>", "", html)
        doc.add_paragraph(text)


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
    now = datetime.now()

    _fill_cover(doc, meta, now)
    _fill_applicability(doc, meta)
    _fill_version_table(doc, meta, vulns, now)
    _fill_target_table(doc, meta, assets or [])
    _fill_schedule_table(doc, meta)
    _fill_summary(doc, meta, vulns)
    _remove_sample_details(doc)
    _append_details(doc, vulns, sections)
    _fit_images(doc)
    _enable_update_fields(doc)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    return out_path
