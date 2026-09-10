"""Word 导入解析：支持两种格式。

1. 固定模板：每个漏洞为一张两列信息表格（/api/v1/imports/template 可下载示例）
   - 表格第一列为字段标签：漏洞名称 / 漏洞等级 / 漏洞类型 / 漏洞链接 / 漏洞描述 / 漏洞证明 / 修复建议
     （标签命名与报告模板「风险问题详情」章节一致；旧模板的 影响URL/复现步骤 仍兼容）
   - 第二列为内容，描述/证明/建议单元格支持多段落与截图
   - 文档中可包含任意数量的漏洞表格，其余段落内容会被忽略
2. 平台报告格式：平台导出的渗透测试（复测）报告，如「20260729综合办公系统渗透测试复测报告.docx」
   - 通过「风险问题详情」标题 + 「风险问题汇总」表识别
   - 解析封面/测试目标表得到系统名、报告日期、是否复测，用于自动生成测试计划
"""
import html as html_mod
import re
import uuid
from pathlib import Path

# XXE 评估结论：python-docx 的 oxml 解析器以 resolve_entities=False 构造，
# 不解析外部/内部实体，故 .docx 导入不存在 XXE 风险；xlsx 侧 openpyxl 同样
# 使用 resolve_entities=False，且安装 defusedxml 后自动启用其安全解析器。
from docx import Document
from docx.oxml.ns import qn
from docx.table import _Cell

from app.constants import IMPORT_LABEL_MAP, VUL_LEVEL_EXPORT, VUL_LEVEL_REVERSE, VUL_TYPE_REVERSE

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


def _run_to_html(run, part, image_dir: Path, url_prefix: str, text: str | None = None) -> str:
    """run → 行内 HTML。text 非 None 时用其替代 run 原文（用于裁掉段首的字段标签）。"""
    pieces: list[str] = []
    # 图片：w:drawing 内的 a:blip r:embed 引用
    for blip in run._element.iter(_A_BLIP):
        rid = blip.get(_R_EMBED)
        if rid:
            url = _save_image(part, rid, image_dir, url_prefix)
            if url:
                pieces.append(f'<img src="{url}">')
    content = html_mod.escape(run.text if text is None else text)
    if content:
        if run.bold:
            content = f"<strong>{content}</strong>"
        if run.italic:
            content = f"<em>{content}</em>"
        pieces.append(content)
    return "".join(pieces)


def _para_to_html(p, part, image_dir: Path, url_prefix: str, skip_label: str = "") -> str:
    """段落 → `<p>` HTML；skip_label 非空时裁掉段首「标签：」及其之前的文字。

    「标签：值」同行写法需要保留标签之后的内容（含图片与格式），故按字符区间逐 run
    裁剪后再渲染，而不是整体丢弃该段落。"""
    start: int | None = None
    if skip_label:
        m = re.match(rf"^\s*{re.escape(skip_label)}\s*[:：]\s*", p.text or "")
        if m is not None:
            start = m.end()
    pos = 0
    pieces: list[str] = []
    for run in p.runs:
        raw = run.text or ""
        run_start, run_end = pos, pos + len(raw)
        pos = run_end
        if start is None:
            keep = raw
        else:
            keep = raw[max(0, start - run_start):] if run_end > start else ""
        pieces.append(_run_to_html(run, part, image_dir, url_prefix, keep))
    inner = "".join(pieces)
    return f"<p>{inner}</p>" if inner.strip() else ""


def _cell_to_html(cell: _Cell, part, image_dir: Path, url_prefix: str) -> str:
    return "".join(_para_to_html(p, part, image_dir, url_prefix) for p in cell.paragraphs)


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
            # 固定模板：等级取自模板「漏洞等级」字段本身，无汇总/详情不一致问题
            "level_source": "template",
            "level_summary_text": "",
            "level_detail_text": "",
            "level_mismatch": False,
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


# ---------- 平台报告格式（渗透测试/复测报告）解析 ----------

_SUMMARY_HEADERS = ("问题等级", "风险类型", "风险问题", "修复状态")
_LEVEL_EXPORT_REVERSE = {v: k for k, v in VUL_LEVEL_EXPORT.items()}  # 超危→10 等报告口径
# 可识别的等级词（严重/高危/中危/低危/安全 + 导出口径 超危），用于详情章节等级取值校验
_LEVEL_WORDS = tuple(dict.fromkeys([*VUL_LEVEL_REVERSE, *_LEVEL_EXPORT_REVERSE]))
# 详情等级取值允许包裹的括号/空白（模板占位行「【超危】【高危】…」不在此列）
_DETAIL_LEVEL_TRIM = "【】[]（）() \t"
# 报告文件名：日期 + 公司/系统名 + 渗透测试(复测)报告 + 可选轮次后缀 -N（同日重复发起复测自动追加 -1/-2）
# 例：20250917中移系统集成有限公司综合办公系统渗透测试复测报告-1.docx → 第二轮复测
_REPORT_NAME_RE = re.compile(r"^(\d{8})?(.*?)(?:渗透测试)?(复测)?报告(?:-(\d+))?$")
# 文件名兜底系统名剥离公司前缀：取最后一个「有限公司」之后的部分（如「中移系统集成有限公司综合办公系统」→「综合办公系统」）
_COMPANY_SUFFIX_RE = re.compile(r"(.*?有限公司)(.*)$")
_COVER_DATE_RE = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$")
_RETEST_LABEL_RE = re.compile(r"^\d*漏洞复测$")
# H3 章节内的字段标签行（归一化后） -> 记录字段
_SECTION_LABELS = {
    "测试状态": "status",
    "漏洞等级": "level",
    "漏洞链接": "affected_url",
    "漏洞描述": "description_html",
    "漏洞证明": "reproduce_html",
    "修复建议": "solution_html",
}
# 「标签：值」同行写法（报告作者书写格式不统一，实测报告中与独立标签行混用）：
# 如「漏洞等级：高危」「漏洞链接：\n1. http://…」，必须要求冒号才认定为标签，
# 避免把「漏洞证明如下所示…」这类正文误判为字段标签。
_SECTION_LABEL_COLON_PATTERNS: list[tuple[str, str, re.Pattern]] = [
    (label, key, re.compile(rf"^\s*{re.escape(label)}\s*[:：]"))
    for label, key in _SECTION_LABELS.items()
]
_RETEST_LABEL_COLON_RE = re.compile(r"^\s*(\d*漏洞复测)\s*[:：]")
# 手工编号的链接前缀（如「1. http://…」），取值时剥离
_URL_LEADING_NUM_RE = re.compile(r"^\s*\d+\s*[.、)）]\s*")


def _find_summary_table(doc: Document):
    """定位「风险问题汇总」表：表头含 问题等级/风险类型/风险问题/修复状态。"""
    for table in doc.tables:
        if not table.rows:
            continue
        headers = [_norm_label(c.text) for c in table.rows[0].cells]
        if all(h in headers for h in _SUMMARY_HEADERS):
            return table
    return None


def is_report_docx(doc: Document) -> bool:
    """判定是否为平台导出的渗透测试（复测）报告格式。"""
    has_detail = any(
        p.style.name.startswith("Heading") and "风险问题详情" in p.text for p in doc.paragraphs
    )
    return has_detail and _find_summary_table(doc) is not None


def parse_report_filename(filename: str) -> dict:
    """从文件名提取报告日期/系统名/是否复测/复测轮次序号。

    文件名示例：20260729综合办公系统渗透测试报告.docx、20251011综合办公系统渗透测试复测报告-1.docx。
    复测轮次序号 retest_round_seq：初测=0；首份复测（无后缀）=1；同日重复复测带 -N 后缀=N+1（如 -1 即第二轮复测）。
    系统名剥离常见公司前缀（最后一个「有限公司」之后），保证与工单 system_name（纯系统名）匹配。
    """
    out = {"report_date": "", "system_name": "", "is_retest": False, "retest_round_seq": 0}
    m = _REPORT_NAME_RE.match(Path(filename or "").stem.strip())
    if not m:
        return out
    if m.group(1):
        d = m.group(1)
        out["report_date"] = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    system_name = m.group(2).strip()
    cm = _COMPANY_SUFFIX_RE.match(system_name)
    if cm and cm.group(2).strip():
        system_name = cm.group(2).strip()
    out["system_name"] = system_name
    out["is_retest"] = bool(m.group(3))
    out["retest_round_seq"] = (int(m.group(4)) + 1) if m.group(4) else (1 if m.group(3) else 0)
    return out


def _parse_cover(doc: Document) -> dict:
    """封面段落（首个标题之前）：公司 / 系统名 / 「渗透测试(复测)报告」 / 日期。"""
    meta = {"system_name": "", "report_date": "", "is_retest": False}
    lines: list[str] = []
    for p in doc.paragraphs:
        if p.style.name.startswith("Heading"):
            break
        if p.text.strip():
            lines.append(p.text.strip())
    for i, t in enumerate(lines):
        if t.endswith("报告") and ("渗透测试" in t or "复测" in t):
            meta["is_retest"] = "复测" in t
            if i >= 1:
                meta["system_name"] = lines[i - 1]
        m = _COVER_DATE_RE.match(t)
        if m:
            meta["report_date"] = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return meta


def _parse_target_table(doc: Document) -> dict:
    """「测试目标」表（首列含 业务系统名称）：系统名 / 被测URL / 被测IP / 被测测试账号。"""
    for table in doc.tables:
        labels = {}
        for row in table.rows:
            if not row.cells:
                continue
            labels.setdefault(_norm_label(row.cells[0].text), row.cells[-1].text.strip())
        if "业务系统名称" in labels:
            return {
                "system_name": labels.get("业务系统名称", ""),
                "target_url": labels.get("被测系统URL", ""),
                "target_ip": labels.get("被测系统IP", ""),
                "test_account": labels.get("被测测试账号", ""),
            }
    return {}


def _parse_schedule_table(doc: Document) -> dict:
    """「时间与人员」表（模板表5）：起始/结束时间 + 参测人员姓名。

    模板结构（含导出报告）：row0 测试工作时间段；row1 起始时间|<值>|结束时间|<值>；
    row3 表头 参测人员|所属部门|人员角色|人员分工；row4+ 各参测人员姓名列。
    解析结果用于回填报告测试周期与工单测试人员（按姓名映射系统账号）。
    """
    meta = {"test_start": "", "test_end": "", "testers": []}
    for table in doc.tables:
        rows = table.rows
        if len(rows) < 5:
            continue
        header = [_norm_label(c.text) for c in rows[3].cells]
        if "参测人员" not in header:
            continue
        for row in rows:
            # 起始/结束时间位于同一行的不同列（如 起始时间|<值>|结束时间|<值>），按标签逐列定位取值
            cells = [_norm_label(c.text) for c in row.cells]
            for i, label in enumerate(cells):
                if label == "起始时间" and i + 1 < len(row.cells):
                    meta["test_start"] = _cell_text(row.cells[i + 1]).strip()
                elif label == "结束时间" and i + 1 < len(row.cells):
                    meta["test_end"] = _cell_text(row.cells[i + 1]).strip()
        for row in rows[4:]:
            name = _cell_text(row.cells[0]).strip()
            if name and name not in meta["testers"]:
                meta["testers"].append(name)
        break
    return meta


def _parse_summary_rows(table) -> list[dict]:
    rows: list[dict] = []
    if table is None:
        return rows
    for row in table.rows[1:]:
        cells = [c.text.strip() for c in row.cells]
        if len(cells) < 4 or not cells[2]:
            continue
        rows.append({
            "level_text": cells[0],
            "type_text": cells[1],
            "title": cells[2],
            "fixed": "已修复" in cells[3],
        })
    return rows


def _map_level_report(text: str) -> int | None:
    """报告口径等级：先按字典（严重/高危…），再按导出口径（超危→10）。"""
    code = _map_level(text)
    if code is not None:
        return code
    t = _norm_label(text)
    for name, c in _LEVEL_EXPORT_REVERSE.items():
        if t and (t in name or name in t):
            return c
    return None


def _level_word(text: str) -> str:
    """从详情章节的等级取值中识别等级词，仅接受「就是等级词本身」的写法。

    模板占位行（如「【超危】【高危】【中危】【低危】」）去掉首尾括号后不等于任一
    等级词，一律忽略，避免把占位行误当成详情等级。
    """
    t = _norm_label(text).strip(_DETAIL_LEVEL_TRIM)
    return t if t in _LEVEL_WORDS else ""


def _fuzzy_type(text: str) -> int:
    """类型模糊匹配：精确/包含未命中时按公共字符数取最优（如 权限跨越→权限绕过）。"""
    code = _map_type(text)
    if code is not None:
        return code
    t = _norm_label(text)
    best, best_score = 75, 0
    for name, c in VUL_TYPE_REVERSE.items():
        score = len(set(t) & set(name))
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 2 else 75


def _normalize_vul_title(raw_title: str) -> tuple[str, bool]:
    """归一化报告中的漏洞标题，并判定该条记录是否「已修复」。

    - 剥掉结尾括号里的修复/整改状态后缀（含修饰词，如「（部分未修复）」「（基本已修复）」），
      使同一漏洞在初测/多轮复测报告中标题一致，从而支持跨报告去重合并。
    - fixed 判定：仅当标题明确「已修复/已整改」且不含「部分/未修复/未整改」等否定或部分修饰时才为 True。
    """
    raw_title = (raw_title or "").strip()
    title = raw_title
    # 循环剥掉结尾的修复/整改状态括号（兼容嵌套，如「（部分未修复）（未修复）」）
    while True:
        stripped = re.sub(r"[（(][^（）()]*(?:修复|整改)[^（）()]*[)）]\s*$", "", title).strip()
        if stripped == title:
            break
        title = stripped
    fixed = (
        ("已修复" in raw_title or "已整改" in raw_title)
        and "部分" not in raw_title
        and "基本" not in raw_title
        and "大部分" not in raw_title
        and "未修复" not in raw_title
        and "未整改" not in raw_title
    )
    return title or raw_title, fixed


def _match_section_label(text: str) -> tuple[str | None, str]:
    """识别段落是否为「风险问题详情」字段标签，返回 (记录字段, 命中的标签原文)。

    标签存在两种书写形态，均需支持（实测同一份报告中两种写法混用）：
    - 独占一段：`漏洞链接：` → 值在后续段落，返回的标签原文为空；
    - 与值同段：`漏洞等级：高危`、`漏洞链接：\\n1. http://…` → 值在本段，返回的标签
      原文非空，调用方据此从本段取出同行值（否则该字段会被整体丢弃）。
    """
    norm = _norm_label(text)
    if norm in _SECTION_LABELS:
        return _SECTION_LABELS[norm], ""
    if _RETEST_LABEL_RE.match(norm):
        return "retest_html", ""
    m = _RETEST_LABEL_COLON_RE.match(text or "")
    if m:
        return "retest_html", m.group(1)
    for label, key, pattern in _SECTION_LABEL_COLON_PATTERNS:
        if pattern.match(text or ""):
            return key, label
    return None, ""


def _inline_value(text: str, label: str) -> str:
    """取「标签：值」同段中的值部分（保留原始字符，不归一化以免破坏 URL 中的冒号）。"""
    m = re.match(rf"^\s*{re.escape(label)}\s*[:：]\s*([\s\S]*)$", text or "")
    return m.group(1).strip() if m else ""


def _clean_url(value: str) -> str:
    """去掉手工编号前缀（如「1. http://…」），保证入库为可直接访问的链接。"""
    return _URL_LEADING_NUM_RE.sub("", (value or "").strip())


# 汇总表标题模糊匹配阈值：最长公共子串长度下限 + 相似度（LCS / 较短标题长度）下限。
# 旧实现按「公共字符集合大小 ≥ 4」判定，会把「RSA私钥泄露」误配到
# 「前端JS泄露SM4加密密钥」（公共字符 {S,泄,露,钥}=4）而取到错误等级。
_SUMMARY_LCS_MIN = 4
_SUMMARY_SIMILARITY_MIN = 0.6


def _longest_common_substring_len(a: str, b: str) -> int:
    """最长公共子串长度（动态规划；标题为短文本，开销可忽略）。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for ca in a:
        cur = [0] * (len(b) + 1)
        for j, cb in enumerate(b, start=1):
            if ca == cb:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def _match_summary(summary: list[dict], title: str) -> dict | None:
    """按标题匹配汇总表行：先精确包含，再按「最长公共子串 + 相似度」唯一匹配。

    候选行须同时满足 LCS 长度与相似度阈值，且只有唯一候选才算命中——
    命中多条视为歧义（返回 None），避免张冠李戴取到无关行的等级。
    """
    t = _norm_label(title)
    if not t:
        return None
    for row in summary:
        rt = _norm_label(row["title"])
        if rt and (t in rt or rt in t):
            return row
    hits: list[dict] = []
    for row in summary:
        rt = _norm_label(row["title"])
        if not rt:
            continue
        score = _longest_common_substring_len(t, rt)
        if score < _SUMMARY_LCS_MIN:
            continue
        if score / min(len(t), len(rt)) >= _SUMMARY_SIMILARITY_MIN:
            hits.append(row)
    return hits[0] if len(hits) == 1 else None


def parse_report_docx(file_path: str, image_dir: str, image_url_prefix: str,
                      filename: str = "") -> tuple[dict, list[dict]]:
    """解析平台报告格式文档，返回 (meta, records)。

    meta: {system_name, report_date, is_retest, target_url, target_ip}
    records 字段与 parse_docx 一致，另含 retest_html / fixed。
    """
    doc = Document(file_path)
    part = doc.part
    img_dir = Path(image_dir)

    # meta：封面优先，文件名兜底，测试目标表补齐系统名与 URL/IP，
    # 时间与人员表补齐测试周期与参测人员。
    # 封面/文件名系统名含乱码（U+FFFD）时视为无效，回退到下一数据源，保证能匹配现有工单
    meta = {"system_name": "", "report_date": "", "is_retest": False, "target_url": "", "target_ip": "",
            "test_account": "", "retest_round_seq": 0, "test_start": "", "test_end": "", "testers": []}
    from_name = parse_report_filename(filename or Path(file_path).name)
    cover = _parse_cover(doc)
    target = _parse_target_table(doc)
    schedule = _parse_schedule_table(doc)

    def _clean(name: str) -> str:
        name = (name or "").strip()
        return "" if "\ufffd" in name else name

    meta["system_name"] = (_clean(cover["system_name"])
                           or _clean(from_name["system_name"])
                           or _clean(target.get("system_name", "")))
    meta["report_date"] = cover["report_date"] or from_name["report_date"]
    meta["is_retest"] = cover["is_retest"] or from_name["is_retest"]
    meta["retest_round_seq"] = from_name.get("retest_round_seq", 0)
    meta["target_url"] = target.get("target_url", "")
    meta["target_ip"] = target.get("target_ip", "")
    meta["test_account"] = target.get("test_account", "")
    meta["test_start"] = schedule.get("test_start", "")
    meta["test_end"] = schedule.get("test_end", "")
    meta["testers"] = schedule.get("testers", [])

    # 切分「风险问题详情」下的 H3 漏洞章节
    sections: list[tuple[str, list]] = []
    in_detail = False
    current: list | None = None
    for p in doc.paragraphs:
        style = p.style.name or ""
        if style.startswith("Heading"):
            if "风险问题详情" in p.text:
                in_detail = True
                current = None
            elif in_detail and style == "Heading 3":
                current = []
                sections.append((p.text.strip(), current))
            else:
                in_detail = False
                current = None
            continue
        if current is not None:
            current.append(p)

    summary = _parse_summary_rows(_find_summary_table(doc))
    records: list[dict] = []
    for idx, (raw_title, paras) in enumerate(sections):
        title, fixed = _normalize_vul_title(raw_title)
        record: dict = {
            "title": title,
            "level": 30,
            "vul_type": 75,
            "affected_url": "",
            "description_html": "",
            "reproduce_html": "",
            "solution_html": "",
            "retest_html": "",
            "fixed": fixed,
            "errors": [],
            # 等级来源追溯：detail（风险问题详情）/ summary（风险问题汇总）/ default（中危兜底）
            "level_source": "default",
            "level_summary_text": "",
            "level_detail_text": "",
            "level_mismatch": False,
        }
        bucket: str | None = None
        detail_level_text = ""
        for p in paras:
            key, label = _match_section_label(p.text)
            if key is not None:
                bucket = key
                if not label:
                    continue
                # 「标签：值」同行写法：实测报告中与独立标签行混用，同行值必须取用，
                # 否则漏洞等级 / 漏洞链接会随该段整体丢失
                inline = _inline_value(p.text, label)
                if bucket == "level":
                    detail_level_text = _level_word(inline) or detail_level_text
                    bucket = None
                elif bucket == "status":
                    bucket = None
                elif bucket == "affected_url":
                    if inline and not record["affected_url"]:
                        record["affected_url"] = _clean_url(inline)[:512]
                    bucket = None
                else:
                    record[bucket] += _para_to_html(
                        p, part, img_dir, image_url_prefix, skip_label=label
                    )
                continue
            if bucket == "level":
                # 「漏洞等级：」独立标签行 + 值另起一行的写法
                if not detail_level_text:
                    detail_level_text = _level_word(p.text)
                continue
            if bucket in ("description_html", "reproduce_html", "solution_html", "retest_html"):
                inner = "".join(_run_to_html(r, part, img_dir, image_url_prefix) for r in p.runs)
                if inner.strip():
                    record[bucket] += f"<p>{inner}</p>"
            elif bucket == "affected_url" and not record["affected_url"] and p.text.strip():
                record["affected_url"] = _clean_url(p.text)[:512]
            # status 桶为模板选项占位行（如【超危】【高危】…），测试状态以漏洞字段为准

        record["level_detail_text"] = detail_level_text
        # 等级/类型/修复状态优先取汇总表：数量一致按序配对，否则按标题匹配
        row = summary[idx] if len(summary) == len(sections) else _match_summary(summary, title)
        if row is not None:
            record["level_summary_text"] = row["level_text"]
            record["vul_type"] = _fuzzy_type(row["type_text"])
            record["fixed"] = record["fixed"] or row["fixed"]
        # 等级来源优先级（D1）：风险问题详情等级 > 汇总表匹配等级 > 中危兜底。
        # 详情是漏洞自身的权威描述；汇总表常与详情不一致（甚至两处漏洞集合不同），
        # 匹配失败时旧实现静默回落中危，导致等级被误判
        detail_level = _map_level_report(detail_level_text) if detail_level_text else None
        summary_level = _map_level_report(row["level_text"]) if row is not None else None
        if detail_level is not None:
            record["level"] = detail_level
            record["level_source"] = "detail"
            # 报告存在汇总表却与该漏洞对不上（未匹配到行）同样属「汇总与详情不一致」，
            # 一并标记提醒：此类报告常因汇总表与详情不是同一批漏洞而导致等级误判
            record["level_mismatch"] = bool(summary) and summary_level != detail_level
        elif summary_level is not None:
            record["level"] = summary_level
            record["level_source"] = "summary"
        else:
            record["level"] = 30
            record["level_source"] = "default"
            if row is None:
                record["errors"].append(
                    "未在「风险问题汇总」表中匹配到该漏洞，且风险问题详情未给出漏洞等级，已按中危处理"
                )
            else:
                record["errors"].append(f"无法识别漏洞等级「{row['level_text']}」，已按中危处理")
        records.append(record)

    return meta, records


def parse_any_docx(file_path: str, image_dir: str, image_url_prefix: str,
                   filename: str = "") -> tuple[str, dict | None, list[dict]]:
    """自动识别文档格式并解析。

    返回 (doc_kind, meta, records)：报告格式为 ("report", meta, records)，
    否则按固定模板解析为 ("template", None, records)。
    """
    doc = Document(file_path)
    if is_report_docx(doc):
        meta, records = parse_report_docx(file_path, image_dir, image_url_prefix, filename)
        return "report", meta, records
    return "template", None, parse_docx(file_path, image_dir, image_url_prefix)


def build_import_template() -> Document:
    """生成标准导入模板文档（含填写示例），字段与报告模板「风险问题详情」章节一致。"""
    doc = Document()
    doc.add_heading("漏洞导入模板", level=0)
    doc.add_paragraph("填写说明：每个漏洞使用一张下方格式的表格，可复制多份；"
                      "表格以外的内容不会被导入。漏洞等级取值：严重/高危/中危/低危。"
                      "字段名称与导出报告的「风险问题详情」章节一致，导入后可直接生成报告。")

    rows = [
        ("漏洞名称", "示例：后台登录接口存在SQL注入"),
        ("漏洞等级", "高危"),
        ("漏洞类型", "SQL注入漏洞"),
        ("漏洞链接", "https://example.com/api/login"),
        ("漏洞描述", "在此填写漏洞描述，可包含多段文字与截图。"),
        ("漏洞证明", "1. 打开登录页\n2. 在用户名输入 ' or 1=1--\n3. 观察返回（可粘贴截图作为证明）"),
        ("修复建议", "使用参数化查询，过滤特殊字符。"),
    ]
    table = doc.add_table(rows=len(rows), cols=2)
    table.style = "Table Grid"
    for i, (label, value) in enumerate(rows):
        table.rows[i].cells[0].text = label
        table.rows[i].cells[1].text = value
    return doc
