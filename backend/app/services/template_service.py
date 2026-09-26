"""报告模板中心（P1-4）：模板校验、版本与启用选择、示例数据试生成。

模板锚点契约（与 `report_builder` 的填充逻辑一一对应，模板必须保持表序不变）：

    表0 封面装饰 | 表1 版本变更记录 | 表2 适用性声明 | 表3 目录(TOC)
    表4 测试目标 | 表5 时间与人员 | 表6 风险问题汇总

**发布前校验**：占位符（锚点表）缺失时阻止发布并给出字段清单；
**版本策略**：同一名称下同时只有一个启用版本，发布新版本自动停用旧版本，
回滚 = 重新启用旧版本（禁止直接覆盖正在使用的文件）；
**回退**：无可用模板时导出回退包内默认模板，系统始终可导出。
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.storage import resolve_storage_path
from app.models import ReportTemplate

logger = logging.getLogger(__name__)

# 必需锚点表：(表序号, 说明)
REQUIRED_TABLES: tuple[tuple[int, str], ...] = (
    (0, "封面装饰表"),
    (1, "版本变更记录表"),
    (2, "适用性声明表"),
    (3, "目录（TOC）表"),
    (4, "测试目标表"),
    (5, "时间与人员表"),
    (6, "风险问题汇总表"),
)

# 示例数据试生成用的假漏洞/章节（不落库，仅用于模板可用性预览）
_SAMPLE_META = {
    "title": "模板试生成示例报告",
    "project_name": "示例项目",
    "customer": "示例客户",
    "author": "Talos",
    "test_start": "2026-01-01",
    "test_end": "2026-01-05",
    "target_ip": "192.0.2.10",
    "test_account": "demo / demo",
    "is_retest": False,
    "testers": ["张三", "李四"],
    "report_records": [],
}
_SAMPLE_SECTIONS = [
    {"title": "示例漏洞：模板占位符校验", "vul_id": 1,
     "content_html": "<p>这是模板试生成使用的示例章节内容。</p>"},
]
_SAMPLE_VULNS = [
    {"id": 1, "title": "示例漏洞：模板占位符校验", "vul_type": 75, "level": 20,
     "status": 10, "affected_url": "https://example.com/demo", "is_retest": False,
     "retest_html": ""},
]


def validate_docx(path: str | Path) -> tuple[bool, list[str], list[dict]]:
    """校验模板 docx 的锚点结构，返回 `(是否通过, 缺失清单, 锚点信息)`。"""
    from docx import Document

    try:
        doc = Document(str(path))
    except Exception as exc:  # noqa: BLE001  损坏/非 docx
        logger.warning("模板解析失败: %s", exc)
        raise HTTPException(400, "模板文件无法解析，请确认为有效的 .docx 文档") from exc

    missing: list[str] = []
    anchors: list[dict] = []
    tables = doc.tables
    for index, desc in REQUIRED_TABLES:
        if index >= len(tables):
            missing.append(f"{desc}（第 {index} 个表格缺失）")
            continue
        table = tables[index]
        if not table.rows:
            missing.append(f"{desc}（第 {index} 个表格为空）")
            continue
        anchors.append({
            "index": index, "desc": desc,
            "rows": len(table.rows), "cols": len(table.columns),
        })
    return (not missing), missing, anchors


def preview_docx(template_path: str | Path) -> str:
    """用示例数据试生成 docx，返回 storage 相对路径（`uploads/previews/<uuid>.docx`）。"""
    from app.services.report_builder import build_report_docx

    name = f"{uuid.uuid4().hex}.docx"
    rel_path = f"uploads/previews/{name}"
    dest_dir = settings.storage_sub("uploads", "previews")
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = settings.storage_path / rel_path
    build_report_docx(
        dict(_SAMPLE_META), list(_SAMPLE_VULNS), list(_SAMPLE_SECTIONS),
        str(out), [], [], template_path=str(template_path),
    )
    return rel_path


async def pick_template(
    session: AsyncSession, report_type: str = "",
) -> ReportTemplate | None:
    """选择导出模板：优先匹配报告类型，其次通用模板；无启用模板返回 None（走包内默认）。"""
    rows = (
        await session.execute(
            select(ReportTemplate).where(ReportTemplate.is_active.is_(True))
            .order_by(ReportTemplate.id.desc())
        )
    ).scalars().all()
    if not rows:
        return None
    if report_type:
        for row in rows:
            if row.report_type == report_type:
                return row
    for row in rows:
        if row.report_type == "all":
            return row
    return rows[0]


def template_file(row: ReportTemplate | None) -> str | None:
    """模板文件绝对路径；无模板或文件已被清理时返回 None（调用方回退包内默认模板）。"""
    if row is None or not row.file_path:
        return None
    try:
        return str(resolve_storage_path(row.file_path, not_found_detail="模板文件已被清理"))
    except HTTPException:
        logger.warning("模板文件不可用，回退包内默认模板 template_id=%s", row.id)
        return None


async def deactivate_siblings(
    session: AsyncSession, row: ReportTemplate, *, except_id: int | None = None,
) -> None:
    """同一名称下只保留一个启用版本。"""
    siblings = (
        await session.execute(select(ReportTemplate).where(ReportTemplate.name == row.name))
    ).scalars().all()
    for item in siblings:
        if item.id != (except_id or row.id):
            item.is_active = False
