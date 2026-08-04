"""专项管理 API：远程检测 / 测试计划 / 春耕行动，统一 special:manage 权限。"""
import re
from datetime import timedelta
from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import TESTING_PLAN_STATUS, PlanStatus
from app.core.deps import require_perm
from app.core.query import get_or_404, paginate, apply_sort
from app.core.sanitize import excel_safe
from app.core.timeutil import utcnow
from app.db import get_session
from app.models import (
    RemoteTesting,
    Report,
    SpringAction,
    TestingPlan,
    TestingPlanRetestRound,
    User,
    Vul,
    testing_plan_testers,
)
from app.schemas import (
    Page,
    PlanImportResultOut,
    RemoteTestingIn,
    RemoteTestingOut,
    SpringActionIn,
    SpringActionOut,
    TestingPlanIn,
    TestingPlanOut,
)
from app.services import plan_service

router = APIRouter(tags=["专项管理"])


# ---------- 远程检测 ----------
@router.get("/remote-testings", response_model=Page[RemoteTestingOut])
async def list_remote_testings(
    search: str = "",
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(
            RemoteTesting.title.ilike(f"%{search}%")
            | RemoteTesting.system_name.ilike(f"%{search}%")
            | RemoteTesting.department.ilike(f"%{search}%")
        )
    stmt = select(RemoteTesting).where(*cond)
    stmt = apply_sort(
        stmt, RemoteTesting, sort, order,
        {"id", "title", "system_name", "test_time", "department", "appeal_success", "create_time"},
        RemoteTesting.id.desc(),
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=items)


async def _check_appeal_report(session: AsyncSession, report_id: int | None) -> None:
    if report_id is not None and await session.get(Report, report_id) is None:
        raise HTTPException(400, "指定的申诉报告不存在")


@router.post("/remote-testings", response_model=RemoteTestingOut)
async def create_remote_testing(
    body: RemoteTestingIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    await _check_appeal_report(session, body.appeal_report_id)
    row = RemoteTesting(**body.model_dump(), creator_id=user.id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.put("/remote-testings/{row_id}", response_model=RemoteTestingOut)
async def update_remote_testing(
    row_id: int,
    body: RemoteTestingIn,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, RemoteTesting, row_id, "远程检测记录不存在")
    await _check_appeal_report(session, body.appeal_report_id)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/remote-testings/{row_id}")
async def delete_remote_testing(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(RemoteTesting, row_id)
    if row:
        await session.delete(row)
        await session.commit()
    return {"msg": "删除成功"}


# ---------- 测试计划 ----------
def _plan_conditions(
    search: str = "",
    status: int | None = None,
    test_type: str = "",
    department: str = "",
    receive_from: str = "",
    receive_to: str = "",
    tester_id: int | None = None,
    unclaimed: bool = False,
) -> list:
    """测试计划筛选条件，供列表/统计/导出共用。receive_time 为 YYYY-MM-DD 字符串，直接比较。

    tester_id 非空时过滤「当前可测试系统」：当前用户为测试人且状态为初测中/复测申请/复测中。
    unclaimed 为真时过滤「无人认领的测试」：测试人员列表为空。
    两者同时启用时按并集处理：满足任一条件的记录均展示。
    """
    cond = []
    if search:
        cond.append(
            TestingPlan.system_name.ilike(f"%{search}%")
            | TestingPlan.department.ilike(f"%{search}%")
            | TestingPlan.test_type.ilike(f"%{search}%")
        )
    if status is not None:
        cond.append(TestingPlan.status == status)
    if test_type:
        cond.append(TestingPlan.test_type == test_type)
    if department:
        cond.append(TestingPlan.department == department)
    if receive_from:
        cond.append(TestingPlan.receive_time >= receive_from)
    if receive_to:
        # 空 receive_time 恒小于任意日期串，仅需上界比较时排除空值
        cond.append(TestingPlan.receive_time != "")
        cond.append(TestingPlan.receive_time <= receive_to)
    if tester_id is not None and unclaimed:
        # 并集：当前可测试系统 OR 无人认领（与其他筛选条件保持 AND）
        cond.append(
            or_(
                and_(
                    TestingPlan.status.in_([
                        PlanStatus.TESTING, PlanStatus.RETEST_APPLY, PlanStatus.RETESTING,
                    ]),
                    exists().where(
                        testing_plan_testers.c.testing_plan_id == TestingPlan.id,
                        testing_plan_testers.c.user_id == tester_id,
                    ),
                ),
                ~exists().where(testing_plan_testers.c.testing_plan_id == TestingPlan.id),
            )
        )
    elif tester_id is not None:
        cond.append(
            TestingPlan.status.in_([
                PlanStatus.TESTING, PlanStatus.RETEST_APPLY, PlanStatus.RETESTING,
            ])
        )
        cond.append(
            exists().where(
                testing_plan_testers.c.testing_plan_id == TestingPlan.id,
                testing_plan_testers.c.user_id == tester_id,
            )
        )
    elif unclaimed:
        cond.append(
            ~exists().where(testing_plan_testers.c.testing_plan_id == TestingPlan.id)
        )
    return cond


def _month_range(start: str, end: str) -> list[str]:
    """由 YYYY-MM-DD 起止生成 YYYY-MM 月份序列（含首尾，上限 120 个月）。"""
    try:
        y1, m1 = int(start[:4]), int(start[5:7])
        y2, m2 = int(end[:4]), int(end[5:7])
    except (ValueError, IndexError):
        return []
    months: list[str] = []
    y, m = y1, m1
    while (y, m) <= (y2, m2) and len(months) < 120:
        months.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return months


async def _compute_plan_stats(
    session: AsyncSession, cond: list, receive_from: str, receive_to: str
) -> dict:
    """按筛选条件计算测试计划多维度统计，供 stats 端点与导出汇总共用。"""
    plan_ids_stmt = select(TestingPlan.id).where(*cond)

    by_status_rows = (
        await session.execute(
            select(TestingPlan.status, func.count(TestingPlan.id))
            .where(*cond)
            .group_by(TestingPlan.status)
        )
    ).all()
    by_status = [
        {"status": s, "name": TESTING_PLAN_STATUS.get(s, str(s)), "count": c}
        for s, c in sorted(by_status_rows)
    ]
    total_plans = sum(c for _, c in by_status_rows)
    retest_done_plans = sum(c for s, c in by_status_rows if s == PlanStatus.RETEST_DONE)
    # 初测次数：达到「初测中」及之后状态的计划各记一次初测
    first_test_count = sum(c for s, c in by_status_rows if s >= PlanStatus.TESTING)

    retest_count = (
        await session.execute(
            select(func.count(TestingPlanRetestRound.id)).where(
                TestingPlanRetestRound.plan_id.in_(plan_ids_stmt)
            )
        )
    ).scalar_one()

    # 人天统计：预估/实际总和；剩余预估人天仅统计未测试状态计划的预估人天之和
    est_mandays_total = (
        await session.execute(select(func.coalesce(func.sum(TestingPlan.est_mandays), 0.0)).where(*cond))
    ).scalar_one()
    actual_mandays_total = (
        await session.execute(select(func.coalesce(func.sum(TestingPlan.actual_mandays), 0.0)).where(*cond))
    ).scalar_one()
    remaining_est_mandays = (
        await session.execute(
            select(func.coalesce(func.sum(TestingPlan.est_mandays), 0.0)).where(
                *cond, TestingPlan.status == PlanStatus.UNTESTED
            )
        )
    ).scalar_one()

    # 按月漏洞数：筛选后计划关联漏洞按提交月份聚合（数据库无关：应用层聚合）
    months = _month_range(receive_from, receive_to) if receive_from and receive_to else []
    if not months:
        now = utcnow()
        months = sorted(
            {(now.replace(day=1) - timedelta(days=30 * i)).strftime("%Y-%m") for i in range(12)}
        )
    monthly = {m: 0 for m in months}
    submit_rows = (
        await session.execute(
            select(Vul.submit_time).where(Vul.testing_plan_id.in_(plan_ids_stmt))
        )
    ).scalars().all()
    for submit_time in submit_rows:
        if submit_time is None:
            continue
        key = submit_time.strftime("%Y-%m")
        if key in monthly:
            monthly[key] += 1

    return {
        "total_plans": total_plans,
        "retest_done_plans": retest_done_plans,
        "first_test_count": first_test_count,
        "retest_count": retest_count,
        "total_test_count": first_test_count + retest_count,
        "est_mandays_total": round(float(est_mandays_total), 2),
        "actual_mandays_total": round(float(actual_mandays_total), 2),
        "remaining_est_mandays": round(float(remaining_est_mandays), 2),
        "by_status": by_status,
        "vulns_by_month": [{"month": m, "count": c} for m, c in monthly.items()],
    }


@router.get("/testing-plans", response_model=Page[TestingPlanOut])
async def list_testing_plans(
    search: str = "",
    status: int | None = None,
    test_type: str = "",
    department: str = "",
    receive_from: str = "",
    receive_to: str = "",
    my_tests: bool = False,
    unclaimed: bool = False,
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """测试计划列表。my_tests 显示当前可测试系统，unclaimed 显示无人认领的测试。"""
    cond = _plan_conditions(
        search, status, test_type, department, receive_from, receive_to,
        tester_id=user.id if my_tests else None,
        unclaimed=unclaimed,
    )
    stmt = select(TestingPlan).where(*cond)
    stmt = apply_sort(
        stmt, TestingPlan, sort, order,
        {"id", "system_name", "plan_name", "test_type", "department", "status", "est_mandays",
         "actual_mandays", "receive_time", "retest_done_time", "create_time"},
        TestingPlan.id.desc(),
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=items)


@router.get("/testing-plans/stats")
async def testing_plan_stats(
    search: str = "",
    status: int | None = None,
    test_type: str = "",
    department: str = "",
    receive_from: str = "",
    receive_to: str = "",
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """测试计划多维度统计：总数/复测完成数/初测次数/复测次数/总测试次数/状态分布/按月漏洞数。"""
    cond = _plan_conditions(search, status, test_type, department, receive_from, receive_to)
    return await _compute_plan_stats(session, cond, receive_from, receive_to)


PLAN_EXCEL_HEADERS = [
    "ID", "测试计划名称", "测试系统", "测试类型", "所属部门",
    "工单ID", "工单提起时间", "状态", "测试人员",
    "需求接收", "初测完成", "复测通知", "复测完成",
    "预估人天", "实际人天",
    "超危数", "高危数", "中危数", "低危数", "复测轮数",
]


@router.get("/testing-plans/export")
async def export_testing_plans(
    search: str = "",
    status: int | None = None,
    test_type: str = "",
    department: str = "",
    receive_from: str = "",
    receive_to: str = "",
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """导出筛选后的测试计划明细与统计汇总（双 sheet Excel）。"""
    from openpyxl import Workbook

    cond = _plan_conditions(search, status, test_type, department, receive_from, receive_to)
    plans = (
        await session.execute(select(TestingPlan).where(*cond).order_by(TestingPlan.id))
    ).scalars().all()
    stats = await _compute_plan_stats(session, cond, receive_from, receive_to)

    wb = Workbook()
    ws = wb.active
    ws.title = "测试计划"
    ws.append(PLAN_EXCEL_HEADERS)
    for p in plans:
        ws.append([excel_safe(v) for v in (
            p.id, p.plan_name, p.system_name, p.test_type, p.department,
            p.ticket_id, p.ticket_time,
            TESTING_PLAN_STATUS.get(p.status, str(p.status)),
            "、".join(u.realname or u.username for u in p.testers),
            p.receive_time, p.first_test_done_time, p.retest_notice_time, p.retest_done_time,
            p.est_mandays, p.actual_mandays,
            p.stat_critical, p.stat_high, p.stat_medium, p.stat_low,
            p.retest_round_count,
        )])

    ws2 = wb.create_sheet("统计汇总")
    ws2.append(["指标", "数值"])
    ws2.append(["测试计划总数", stats["total_plans"]])
    ws2.append(["复测完成计划数", stats["retest_done_plans"]])
    ws2.append(["初测次数", stats["first_test_count"]])
    ws2.append(["复测次数", stats["retest_count"]])
    ws2.append(["总测试次数（初测+复测）", stats["total_test_count"]])
    ws2.append(["预估人天总计", stats["est_mandays_total"]])
    ws2.append(["实际人天总计", stats["actual_mandays_total"]])
    ws2.append(["剩余预估人天（未测试）", stats["remaining_est_mandays"]])
    ws2.append([])
    ws2.append(["状态", "计划数"])
    for row in stats["by_status"]:
        ws2.append([row["name"], row["count"]])
    ws2.append([])
    ws2.append(["月份", "漏洞数"])
    for row in stats["vulns_by_month"]:
        ws2.append([row["month"], row["count"]])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = "测试计划导出.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


PLAN_STATUS_REVERSE = {v: k for k, v in TESTING_PLAN_STATUS.items()}


def _to_float(text: str) -> float:
    try:
        return float(text) if text else 0.0
    except ValueError:
        return 0.0


def _to_int(text: str) -> int:
    try:
        return int(float(text)) if text else 0
    except ValueError:
        return 0


@router.get("/testing-plans/import/template")
async def download_plan_import_template(_: User = Depends(require_perm("special:manage"))):
    """下载测试计划导入模板（列与导出一致，ID 留空则新增）。"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "测试计划"
    ws.append(PLAN_EXCEL_HEADERS)
    ws.append([
        "", "示例测试计划", "示例商城系统", "渗透测试", "电商事业部",
        "", "2026-01-01", "未测试", "张三、李四",
        "2026-01-01", "", "", "",
        5, 0,
        0, 0, 0, 0, 0,
    ])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = "测试计划导入模板.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/testing-plans/import", response_model=PlanImportResultOut)
async def import_testing_plans(
    file: UploadFile,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """导入历史测试计划：按 ID 更新，无 ID 则新增（upsert）。测试人员按姓名/用户名匹配。"""
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(400, "仅支持 .xlsx 格式的 Excel 文件")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过 20MB")

    from openpyxl import load_workbook

    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "Excel 文件解析失败，请使用导入模板")

    # 预加载用户用于测试人员匹配（姓名优先，其次用户名）
    users = (await session.execute(select(User))).scalars().all()
    user_map: dict[str, User] = {}
    for u in users:
        if u.realname:
            user_map.setdefault(u.realname, u)
        user_map.setdefault(u.username, u)

    # 预加载工单ID占用表（手动值或自动生成值均计入），用于导入时的唯一性校验
    occupied: dict[str, int | str] = {}
    for p in (await session.execute(select(TestingPlan))).scalars().all():
        tid = p.ticket_id
        if tid:
            occupied[tid] = p.id

    ws = wb.active
    result = PlanImportResultOut()
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        cells = [str(c).strip() if c is not None else "" for c in row]
        cells += [""] * (len(PLAN_EXCEL_HEADERS) - len(cells))
        if not any(cells):
            continue
        result.total += 1
        system_name = cells[2]
        if not system_name:
            result.failed += 1
            result.errors.append(f"第{idx}行：测试系统为必填项")
            continue

        row_id = _to_int(cells[0])
        plan = await session.get(TestingPlan, row_id) if row_id else None
        is_new = plan is None
        if is_new:
            plan = TestingPlan(creator_id=user.id)
            session.add(plan)

        plan.plan_name = cells[1]
        plan.system_name = system_name
        plan.test_type = cells[3]
        plan.department = cells[4]
        # cells[5] 工单ID：显式填写则作为手动指定值，未填写则保持原值（新记录由系统自动生成）
        plan.ticket_id_manual = cells[5] or plan.ticket_id_manual or ""
        plan.ticket_time = cells[6]
        plan.status = PLAN_STATUS_REVERSE.get(cells[7], PlanStatus.UNTESTED)
        plan.receive_time = cells[9]
        plan.first_test_done_time = cells[10]
        plan.retest_notice_time = cells[11]
        plan.retest_done_time = cells[12]
        plan.est_mandays = _to_float(cells[13])
        plan.actual_mandays = _to_float(cells[14])
        plan.stat_critical = _to_int(cells[15])
        plan.stat_high = _to_int(cells[16])
        plan.stat_medium = _to_int(cells[17])
        plan.stat_low = _to_int(cells[18])
        matched = [user_map[name] for name in cells[8].split("、") if name.strip() and name.strip() in user_map]
        if matched:
            plan.testers = matched
        # 新增或历史数据无序号时按需求接收日期自动补号
        await _assign_ticket_seq(session, plan)

        # 工单ID唯一性校验：与库中或批内其他行重复则整批终止并提示
        tid = plan.ticket_id
        if tid:
            if tid in occupied and occupied[tid] != row_id:
                raise HTTPException(400, f"第{idx}行：工单ID「{tid}」已存在，请更换后重新导入")
            occupied[tid] = "new" if is_new else row_id

        if is_new:
            result.created += 1
        else:
            result.updated += 1
    await session.commit()
    return result


# 注意：需注册在 /testing-plans/stats、/testing-plans/export、/testing-plans/import/template 等静态路径之后，防止路径吞噬
@router.get("/testing-plans/{row_id}", response_model=TestingPlanOut)
async def get_testing_plan(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """单条计划详情（含测试人员/关联漏洞/关联报告/复测轮次），供流程抽屉刷新。"""
    return await get_or_404(session, TestingPlan, row_id, "测试计划不存在")


async def _assign_ticket_seq(session: AsyncSession, row: TestingPlan) -> None:
    """按需求接收日期生成当日录入次序（ticket_seq），无日期时不生成。

    - 新对象 ticket_seq 为 None（SQLAlchemy default 在构造时不生效），
      需用 falsy 判断（None/0 均视为未分配）。
    - 仅当对象已持久化（更新场景）时才排除自身，避免新对象 id 为 None 时
      生成 `id != NULL` 恒为假的 SQL 条件导致序号始终为 1。
    - 手动指定了工单ID时不自动分配序号，避免浪费当日序号。
    """
    if not row.receive_time or row.ticket_seq or row.ticket_id_manual:
        return
    date_like = f"{row.receive_time[:10]}%"
    stmt = select(func.max(TestingPlan.ticket_seq)).where(
        TestingPlan.receive_time.like(date_like)
    )
    if row.id is not None:
        stmt = stmt.where(TestingPlan.id != row.id)
    max_seq = (await session.execute(stmt)).scalar_one()
    row.ticket_seq = (max_seq or 0) + 1


async def _check_ticket_id_unique(
    session: AsyncSession, ticket_id: str, exclude_id: int | None = None
) -> None:
    """校验工单ID唯一性：手动指定值或自动生成值（需求接收日期+序号）均不得与其他记录重复。

    工单ID为派生属性（手动指定优先，否则由 receive_time+ticket_seq 生成），
    无法直接建数据库唯一约束，此处按两种生成方式构造条件做应用层校验。
    """
    if not ticket_id:
        return
    # 手动指定值匹配
    conds = [TestingPlan.ticket_id_manual == ticket_id]
    # 自动生成值匹配：YYYYMMDD-N，对应 receive_time(YYYY-MM-DD) + ticket_seq
    m = re.fullmatch(r"(\d{8})-(\d+)", ticket_id)
    if m:
        date_part, seq = m.group(1), int(m.group(2))
        date_like = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:]}%"
        conds.append(
            and_(
                TestingPlan.receive_time.like(date_like),
                TestingPlan.ticket_seq == seq,
            )
        )
    stmt = select(TestingPlan.id).where(or_(*conds))
    if exclude_id is not None:
        stmt = stmt.where(TestingPlan.id != exclude_id)
    if (await session.execute(stmt)).first() is not None:
        raise HTTPException(400, f"工单ID「{ticket_id}」已存在，请更换后保存")


@router.post("/testing-plans", response_model=TestingPlanOut)
async def create_testing_plan(
    body: TestingPlanIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = TestingPlan(**body.model_dump(), creator_id=user.id)
    await _assign_ticket_seq(session, row)
    await _check_ticket_id_unique(session, row.ticket_id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/testing-plans/{row_id}/claim", response_model=TestingPlanOut)
async def claim_testing_plan(
    row_id: int,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """认领测试计划：当前用户加入测试人员（幂等）；未测试状态自动进入初测中。"""
    row = await get_or_404(session, TestingPlan, row_id, "测试计划不存在")
    if all(u.id != user.id for u in row.testers):
        row.testers.append(user)
    if row.status == 10:
        row.status = 20
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/testing-plans/{row_id}/quit", response_model=TestingPlanOut)
async def quit_testing_plan(
    row_id: int,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """退出认领：当前用户移出测试人员列表。"""
    row = await get_or_404(session, TestingPlan, row_id, "测试计划不存在")
    row.testers = [u for u in row.testers if u.id != user.id]
    await session.commit()
    await session.refresh(row)
    return row


@router.put("/testing-plans/{row_id}", response_model=TestingPlanOut)
async def update_testing_plan(
    row_id: int,
    body: TestingPlanIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, TestingPlan, row_id, "测试计划不存在")
    if body.status != row.status and not plan_service.can_operate(user, row):
        raise HTTPException(403, "仅认领者或管理员可修改测试状态")
    # 手动流转到「复测中」时记一轮复测（已有进行中轮次则不重复计数）
    if body.status == 50 and row.status != 50:
        plan_service.start_retest_round(session, row, "手动流转至复测中", user.id)
    for k, v in body.model_dump().items():
        setattr(row, k, v)
    # 补生成工单ID序号（历史/导入数据无序号时自动补齐）
    await _assign_ticket_seq(session, row)
    # 保存前校验工单ID唯一性（手动指定值或自动生成值均不可重复）
    await _check_ticket_id_unique(session, row.ticket_id, exclude_id=row.id)
    # 有关联漏洞时统计以自动重算为准，覆盖手填值
    if row.vuls:
        await plan_service.refresh_stats(session, row.id)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/testing-plans/{row_id}")
async def delete_testing_plan(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(TestingPlan, row_id)
    if row:
        # 解除漏洞与报告的关联，避免悬挂外键
        await session.execute(
            update(Vul).where(Vul.testing_plan_id == row_id).values(testing_plan_id=None)
        )
        await session.execute(
            update(Report).where(Report.testing_plan_id == row_id).values(testing_plan_id=None)
        )
        await session.delete(row)
        await session.commit()
    return {"msg": "删除成功"}


# ---------- 春耕行动 ----------
async def _load_vulns(session: AsyncSession, vul_ids: list[int]) -> list[Vul]:
    if not vul_ids:
        return []
    vulns = (await session.execute(select(Vul).where(Vul.id.in_(vul_ids)))).scalars().all()
    if len(vulns) != len(set(vul_ids)):
        raise HTTPException(400, "部分漏洞不存在")
    return list(vulns)


@router.get("/spring-actions", response_model=Page[SpringActionOut])
async def list_spring_actions(
    search: str = "",
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(
            SpringAction.report_no.ilike(f"%{search}%")
            | SpringAction.system_name.ilike(f"%{search}%")
            | SpringAction.doc_no.ilike(f"%{search}%")
        )
    stmt = select(SpringAction).where(*cond)
    stmt = apply_sort(
        stmt, SpringAction, sort, order,
        {"id", "report_no", "system_name", "year", "phase", "appeal_success",
         "score_deduction", "doc_no", "create_time"},
        SpringAction.id.desc(),
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=items)


@router.post("/spring-actions", response_model=SpringActionOut)
async def create_spring_action(
    body: SpringActionIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = SpringAction(**body.model_dump(exclude={"vul_ids"}), creator_id=user.id)
    row.vuls = await _load_vulns(session, body.vul_ids)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.put("/spring-actions/{row_id}", response_model=SpringActionOut)
async def update_spring_action(
    row_id: int,
    body: SpringActionIn,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, SpringAction, row_id, "春耕行动记录不存在")
    for k, v in body.model_dump(exclude={"vul_ids"}).items():
        setattr(row, k, v)
    row.vuls = await _load_vulns(session, body.vul_ids)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/spring-actions/{row_id}")
async def delete_spring_action(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(SpringAction, row_id)
    if row:
        await session.delete(row)
        await session.commit()
    return {"msg": "删除成功"}
