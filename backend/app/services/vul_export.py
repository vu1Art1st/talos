"""历史漏洞库 Excel 导出：引用数据批量加载、行映射与工作簿构建。"""
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import SLA_STATES, VUL_LAYER, VUL_LEVEL, VUL_SOURCE, VUL_STATUS, VUL_TYPE, VulStatus
from app.core.sanitize import excel_safe
from app.models import TestingPlan, User, Vul
from app.services import sla_service

# 同步导出上限：超过后要求缩小筛选范围，避免单次请求占用过多内存与 CPU。
MAX_VUL_EXPORT_ROWS = 20_000

VUL_EXPORT_HEADERS = [
    "漏洞ID", "漏洞名称", "漏洞等级", "漏洞类型", "状态", "漏洞来源",
    "所在层", "关联工单ID", "关联工单", "测试类型",
    "关联资产", "归属部门", "系统类型", "影响URL", "CVSS评分",
    "提交人", "提交时间", "通知时间", "修复时间", "修复时限",
    "SLA状态", "SLA剩余/逾期",
]

_DATE_COLUMNS = ("提交时间", "通知时间", "修复时间", "修复时限")
_WIDTHS = {
    "漏洞ID": 10, "漏洞名称": 36, "漏洞等级": 10, "漏洞类型": 18, "状态": 14,
    "漏洞来源": 18, "所在层": 10, "关联工单ID": 12, "关联工单": 24, "测试类型": 14,
    "关联资产": 32, "归属部门": 22, "系统类型": 18, "影响URL": 48, "CVSS评分": 10,
    "提交人": 14, "提交时间": 20, "通知时间": 20, "修复时间": 20, "修复时限": 20,
    "SLA状态": 14, "SLA剩余/逾期": 20,
}


def _joined_unique(values: list[str]) -> str:
    return "、".join(dict.fromkeys(value for value in values if value))


def _status_name(vul: Vul) -> str:
    if vul.status == VulStatus.FIXING and vul.is_retest:
        return "复测未通过"
    return VUL_STATUS.get(vul.status, str(vul.status))


def _source_name(vul: Vul) -> str:
    if vul.testing_plan_id is not None:
        return "渗透测试工单"
    return VUL_SOURCE.get(vul.source) or "未选择"


def _sla_remaining_text(sla: dict) -> str:
    state = sla["sla_state"]
    if state == "none":
        return "-"
    if state == "closed":
        return "已停止计时"
    remaining = sla["sla_remaining_hours"]
    if remaining is None:
        return "-"
    if remaining < 0:
        return f"已逾期 {sla['sla_overdue_days']:g} 天"
    return f"剩余 {remaining:g} 小时"


async def load_reference_maps(
    session: AsyncSession,
    vulns: list[Vul],
) -> tuple[dict[int, tuple[str, str]], dict[int, str]]:
    """批量加载导出引用数据；查询继续受当前用户数据范围约束。"""
    plan_ids = {vul.testing_plan_id for vul in vulns if vul.testing_plan_id is not None}
    plans: dict[int, tuple[str, str]] = {}
    if plan_ids:
        rows = (
            await session.execute(
                select(TestingPlan.id, TestingPlan.system_name, TestingPlan.test_type)
                .where(TestingPlan.id.in_(plan_ids))
            )
        ).all()
        plans = {plan_id: (system_name, test_type) for plan_id, system_name, test_type in rows}

    user_ids = {vul.submitter_id for vul in vulns if vul.submitter_id is not None}
    users: dict[int, str] = {}
    if user_ids:
        rows = (
            await session.execute(
                select(User.id, User.realname, User.username).where(User.id.in_(user_ids))
            )
        ).all()
        users = {user_id: realname or username for user_id, realname, username in rows}
    return plans, users


def build_rows(
    vulns: list[Vul],
    plans: dict[int, tuple[str, str]],
    users: dict[int, str],
    sla_runtime,
) -> list[list]:
    """把漏洞实体映射为 Excel 行，SLA 派生值统一复用 `sla_service.evaluate`。"""
    rows: list[list] = []
    for vul in vulns:
        plan_name, test_type = plans.get(vul.testing_plan_id or 0, ("", ""))
        sla = sla_service.evaluate(vul, sla_runtime)
        rows.append([
            vul.id,
            vul.title,
            VUL_LEVEL.get(vul.level, str(vul.level)),
            VUL_TYPE.get(vul.vul_type, str(vul.vul_type)),
            _status_name(vul),
            _source_name(vul),
            VUL_LAYER.get(vul.layer, str(vul.layer)),
            vul.testing_plan_id or "",
            plan_name,
            test_type,
            _joined_unique([asset.name for asset in vul.assets]),
            _joined_unique([asset.department for asset in vul.assets]),
            _joined_unique([asset.system_type for asset in vul.assets]),
            vul.affected_url,
            vul.score,
            users.get(vul.submitter_id or 0, f"#{vul.submitter_id}" if vul.submitter_id else ""),
            vul.submit_time,
            vul.notice_time,
            vul.fix_time,
            sla["due_at"],
            SLA_STATES.get(sla["sla_state"], sla["sla_state"]),
            _sla_remaining_text(sla),
        ])
    return rows


def build_workbook(rows: list[list]) -> Workbook:
    """构建单 Sheet 工作簿：冻结表头、启用筛选并保持用户文本公式安全。"""
    wb = Workbook()
    ws = wb.active
    ws.title = "历史漏洞库"
    ws.append(VUL_EXPORT_HEADERS)
    for row in rows:
        ws.append([excel_safe(value) for value in row])

    header_fill = PatternFill("solid", fgColor="E8EFE9")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    date_indexes = {VUL_EXPORT_HEADERS.index(name) + 1 for name in _DATE_COLUMNS}
    url_index = VUL_EXPORT_HEADERS.index("影响URL") + 1
    for index, header in enumerate(VUL_EXPORT_HEADERS, start=1):
        ws.column_dimensions[get_column_letter(index)].width = _WIDTHS[header]
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if cell.column in date_indexes and isinstance(cell.value, datetime):
                cell.number_format = "yyyy-mm-dd hh:mm:ss"
            if cell.column == url_index:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
    return wb
