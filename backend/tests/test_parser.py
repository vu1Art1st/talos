"""docx_parser 固定模板解析单元测试。"""
import base64
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.shared import Inches

from app.services.docx_parser import (
    build_import_template,
    is_report_docx,
    parse_any_docx,
    parse_docx,
    parse_report_filename,
)

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


# ---------- 平台报告格式解析 ----------

_SAMPLE_REPORT = Path(__file__).resolve().parents[1] / "storage" / "uploads" / "imports" / "8776123568ad49f885c239c454641a24.docx"


def test_parse_report_filename():
    info = parse_report_filename("20260729综合办公系统渗透测试复测报告.docx")
    assert info == {
        "report_date": "2026-07-29", "system_name": "综合办公系统",
        "is_retest": True, "retest_round_seq": 1,
    }

    info = parse_report_filename("门户系统渗透测试报告.docx")
    assert info["system_name"] == "门户系统"
    assert info["is_retest"] is False
    assert info["report_date"] == ""
    assert info["retest_round_seq"] == 0

    # 同日重复复测带 -N 后缀：-1 表示第二轮复测（round_seq=2）
    info = parse_report_filename("20251011中移系统集成有限公司综合办公系统渗透测试复测报告-1.docx")
    assert info == {
        "report_date": "2025-10-11", "system_name": "综合办公系统",
        "is_retest": True, "retest_round_seq": 2,
    }


def test_normalize_vul_title():
    """标题归一化：剥掉（部分未修复）等修复状态后缀，供跨报告去重合并；fixed 判定严谨。"""
    from app.services.docx_parser import _normalize_vul_title

    # 初测：无后缀，未修复
    assert _normalize_vul_title("越权-劳动合同变更审批") == ("越权-劳动合同变更审批", False)
    # 已修复
    assert _normalize_vul_title("越权-劳动合同变更审批（已修复）") == ("越权-劳动合同变更审批", True)
    # 未修复
    assert _normalize_vul_title("越权-劳动合同变更审批（未修复）") == ("越权-劳动合同变更审批", False)
    # 部分未修复 → 剥后缀且不算已修复
    assert _normalize_vul_title("越权-劳动合同变更审批（部分未修复）") == ("越权-劳动合同变更审批", False)
    # 部分已修复 → 剥后缀且不算已修复（存在未闭环部分）
    assert _normalize_vul_title("越权-劳动合同变更审批（部分已修复）") == ("越权-劳动合同变更审批", False)
    # 基本已修复 → 剥后缀且不算已修复
    assert _normalize_vul_title("越权-劳动合同变更审批（基本已修复）") == ("越权-劳动合同变更审批", False)
    # 半角括号
    assert _normalize_vul_title("越权-劳动合同变更审批(已修复)") == ("越权-劳动合同变更审批", True)
    # 标题含括号但非修复状态 → 不误删
    assert _normalize_vul_title("后台接口存在SQL注入（GET参数）") == ("后台接口存在SQL注入（GET参数）", False)


def test_is_report_docx_on_template(tmp_path: Path):
    """固定模板不应被误判为报告格式。"""
    docx_file = tmp_path / "template.docx"
    build_import_template().save(str(docx_file))
    assert is_report_docx(Document(str(docx_file))) is False


def test_parse_schedule_table():
    """「时间与人员」表：提取测试周期与参测人员；普通文档不误解析。"""
    from app.services.docx_parser import _parse_schedule_table

    doc = Document()
    t = doc.add_table(rows=7, cols=4)
    t.rows[0].cells[0].text = "测试工作时间段"
    t.rows[1].cells[0].text, t.rows[1].cells[1].text = "起始时间", "2026-06-30"
    t.rows[1].cells[2].text, t.rows[1].cells[3].text = "结束时间", "2026-07-01"
    for i, h in enumerate(("参测人员", "所属部门", "人员角色", "人员分工")):
        t.rows[3].cells[i].text = h
    for i, name in enumerate(("邢博宇", "许宁安", "薛田泽")):
        t.rows[4 + i].cells[0].text = name
    assert _parse_schedule_table(doc) == {
        "test_start": "2026-06-30",
        "test_end": "2026-07-01",
        "testers": ["邢博宇", "许宁安", "薛田泽"],
    }

    # 无「时间与人员」表的普通文档返回空值
    plain = Document()
    plain.add_paragraph("普通文档")
    assert _parse_schedule_table(plain) == {"test_start": "", "test_end": "", "testers": []}


def test_parse_target_table():
    """「测试目标」表：解析系统名 / 被测URL / 被测IP / 被测测试账号。"""
    from app.services.docx_parser import _parse_target_table

    doc = Document()
    t = doc.add_table(rows=5, cols=2)
    rows = (
        ("业务系统名称", "综合办公系统"),
        ("被测系统URL", "https://oa.example.com"),
        ("被测系统域名", "oa.example.com"),
        ("被测系统IP", "10.0.0.1"),
        ("被测测试账号", "admin/Admin@123"),
    )
    for i, (label, value) in enumerate(rows):
        t.rows[i].cells[0].text, t.rows[i].cells[1].text = label, value
    assert _parse_target_table(doc) == {
        "system_name": "综合办公系统",
        "target_url": "https://oa.example.com",
        "target_ip": "10.0.0.1",
        "test_account": "admin/Admin@123",
    }


def test_parse_report_docx_sample(tmp_path: Path):
    """样例复测报告：meta 与漏洞记录解析。"""
    if not _SAMPLE_REPORT.exists():
        import pytest
        pytest.skip("样例报告文件不存在")

    assert is_report_docx(Document(str(_SAMPLE_REPORT))) is True

    kind, meta, records = parse_any_docx(
        str(_SAMPLE_REPORT), str(tmp_path / "img"), "/x",
        "20260729综合办公系统渗透测试复测报告.docx",
    )
    assert kind == "report"
    assert meta["system_name"] == "综合办公系统"
    assert meta["report_date"] == "2026-07-29"
    assert meta["is_retest"] is True
    assert meta["target_ip"] == "10.55.133.37"

    assert len(records) == 1
    rec = records[0]
    assert rec["title"].startswith("平行越权")
    assert "已修复" not in rec["title"]  # 标题尾缀被剔除
    assert rec["level"] == 20  # 汇总表：高危
    assert rec["fixed"] is True
    assert rec["affected_url"].startswith("http://10.55.133.37")
    assert rec["description_html"]
    assert rec["retest_html"]  # 「20260729漏洞复测：」段落
    assert rec["errors"] == []


# ---------- 等级来源：风险问题详情优先（回归：曾被静默误判为中危） ----------

def _make_report_docx(path: Path, summary_rows, sections) -> None:
    """构造平台报告格式 docx：风险问题汇总表 + 风险问题详情 H3 章节。

    summary_rows: [(等级, 类型, 漏洞标题, 修复状态)]
    sections: [(章节标题, [段落文本])]
    """
    doc = Document()
    doc.add_heading("风险问题汇总", level=2)
    table = doc.add_table(rows=1 + len(summary_rows), cols=4)
    for i, h in enumerate(("问题等级", "风险类型", "风险问题", "修复状态")):
        table.rows[0].cells[i].text = h
    for i, (level, vtype, title, status) in enumerate(summary_rows, start=1):
        for j, v in enumerate((level, vtype, title, status)):
            table.rows[i].cells[j].text = v
    doc.add_heading("风险问题详情", level=2)
    for title, paras in sections:
        doc.add_heading(title, level=3)
        for text in paras:
            doc.add_paragraph(text)
    doc.save(str(path))


def test_level_word_rejects_placeholder():
    """详情等级取值：只认等级词本身，模板占位行（【超危】【高危】…）不得误取。"""
    from app.services.docx_parser import _level_word

    assert _level_word("高危") == "高危"
    assert _level_word("超危") == "超危"
    assert _level_word("严重") == "严重"
    assert _level_word("【超危】【高危】【中危】【低危】") == ""
    assert _level_word("高危风险") == ""


def test_match_summary_rejects_weak_overlap():
    """汇总表模糊匹配加固：公共字符偶合（RSA私钥泄露 ⊕ 前端JS泄露SM4加密密钥）不得命中。"""
    from app.services.docx_parser import _match_summary

    summary = [{"title": "前端JS泄露SM4加密密钥", "level_text": "中危",
                "type_text": "信息泄露", "fixed": False}]
    assert _match_summary(summary, "RSA私钥泄露") is None
    # 标题包含关系仍应命中
    assert _match_summary(summary, "前端JS泄露SM4加密密钥（未修复）") is not None


def test_report_inline_label_and_detail_level(tmp_path: Path):
    """回归：标签与值同段（「漏洞等级：高危」「漏洞链接：\\n1. http://…」）必须被解析。"""
    docx_file = tmp_path / "inline.docx"
    _make_report_docx(
        docx_file,
        summary_rows=[("高危", "越权", "用户管理存在垂直越权", "未修复")],
        sections=[("用户管理存在垂直越权", [
            "测试状态：初测",
            "漏洞等级：高危",
            "漏洞链接：\n1. http://10.0.0.9/api/user",
            "漏洞描述：",
            "普通用户可越权管理用户。",
        ])],
    )
    _, records = parse_any_docx(str(docx_file), str(tmp_path / "img"), "/x")[1:]
    rec = records[0]
    assert rec["level"] == 20
    assert rec["level_source"] == "detail"
    assert rec["affected_url"] == "http://10.0.0.9/api/user"  # 手工编号前缀被剥离
    assert rec["errors"] == []


def test_report_detail_level_wins_over_unmatched_summary(tmp_path: Path):
    """回归：汇总表与详情章节漏洞集合不同（数量也不齐）时，等级取详情而不是中危兜底。"""
    docx_file = tmp_path / "mismatch.docx"
    _make_report_docx(
        docx_file,
        summary_rows=[
            ("中危", "信息泄露", "前端JS泄露SM4加密密钥", "未修复"),
            ("低危", "配置缺陷", "SourceMap文件泄露", "未修复"),
        ],
        sections=[
            ("RSA私钥泄露", ["测试状态：初测", "漏洞等级：高危", "漏洞证明：", "泄露私钥"]),
            ("平行越权-通知通报-工作通知&风险通报",
             ["测试状态：初测", "漏洞等级：高危", "漏洞证明：", "越权查看通知"]),
            ("垂直越权-数字安全-威胁情报",
             ["测试状态：初测", "漏洞等级：高危", "漏洞证明：", "越权查看情报"]),
        ],
    )
    _, records = parse_any_docx(str(docx_file), str(tmp_path / "img"), "/x")[1:]
    assert len(records) == 3
    assert [r["level"] for r in records] == [20, 20, 20]
    assert all(r["level_source"] == "detail" for r in records)
    assert all(r["errors"] == [] for r in records)
    # 有汇总表却与该漏洞对不上 → 同样标记为「汇总与详情不一致」，供导入前提醒
    assert all(r["level_mismatch"] is True for r in records)
    assert all(r["level_summary_text"] == "" for r in records)


def test_report_level_mismatch_flag(tmp_path: Path):
    """汇总表与详情等级不一致：按序配对后取详情等级，并标记 level_mismatch 供弹窗提醒。"""
    docx_file = tmp_path / "flag.docx"
    _make_report_docx(
        docx_file,
        summary_rows=[("中危", "越权", "平行越权访问项目信息", "未修复")],
        sections=[("平行越权访问项目信息", ["测试状态：初测", "漏洞等级：高危", "漏洞证明：", "越权"])],
    )
    _, records = parse_any_docx(str(docx_file), str(tmp_path / "img"), "/x")[1:]
    rec = records[0]
    assert rec["level"] == 20
    assert rec["level_source"] == "detail"
    assert rec["level_summary_text"] == "中危"
    assert rec["level_detail_text"] == "高危"
    assert rec["level_mismatch"] is True


def test_report_level_medium_fallback_without_any_source(tmp_path: Path):
    """详情与汇总表均无可用等级时才回落中危，并记录 errors 提示人工核对。"""
    docx_file = tmp_path / "fallback.docx"
    _make_report_docx(
        docx_file,
        summary_rows=[("中危", "信息泄露", "前端JS泄露SM4加密密钥", "未修复")],
        sections=[
            ("甲漏洞", ["漏洞描述：", "无等级信息"]),
            ("乙漏洞", ["漏洞描述：", "无等级信息"]),
        ],
    )
    _, records = parse_any_docx(str(docx_file), str(tmp_path / "img"), "/x")[1:]
    assert [r["level"] for r in records] == [30, 30]
    assert all(r["level_source"] == "default" for r in records)
    assert all(r["errors"] for r in records)
