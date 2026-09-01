"""测试计划（渗透测试工单）API：列表/统计/Excel 导入导出与全生命周期流转，统一 special:manage 权限。"""
import html as html_mod
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile
from openpyxl import load_workbook
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import NONPEN_ITEMS, PlanStatus, TESTING_PLAN_STATUS
from app.core.deps import require_any_perm, require_perm
from app.core.query import get_or_404, paginate, apply_sort
from app.core.timeutil import mandays_between
from app.core.timeutil import now as tznow
from app.core.xlsx import xlsx_response
from app.db import get_session
from app.models import (
    Message,
    NonpenPlan,
    Report,
    ReportSection,
    TestingPlan,
    User,
    Vul,
)
from app.schemas import CompleteNoVulnIn, Page, TestingPlanIn, TestingPlanOut
from app.services import nonpen_service, plan_io, plan_query, plan_service, ticket_service, vuln_service
from app.services.audit_service import audit
from app.services.notify_service import notify

router = APIRouter(tags=["专项管理"])


@router.get("/testing-plans", response_model=Page[TestingPlanOut])
async def list_testing_plans(
    search: str = "",
    status: int | None = None,
    test_type: str = "",
    department: str = "",
    receive_from: str = "",
    receive_to: str = "",
    first_test_from: str = "",
    first_test_to: str = "",
    filters: str = "",
    my_tests: bool = False,
    unclaimed: bool = False,
    pending: bool = False,
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(require_any_perm("special:manage", "vuln:submit")),
    session: AsyncSession = Depends(get_session),
):
    """测试计划列表。my_tests 显示当前可测试系统，unclaimed 显示无人认领的测试，pending 显示待办流程。

    filters 为聚合筛选 JSON（详见 plan_query.plan_filters_condition），与上述固定参数按 AND 组合。
    """
    cond = plan_query.plan_conditions(
        search, status, test_type, department, receive_from, receive_to,
        first_test_from=first_test_from, first_test_to=first_test_to,
        tester_id=user.id if my_tests else None,
        unclaimed=unclaimed,
        pending=pending,
    )
    cond += plan_query.plan_filters_condition(filters)
    stmt = select(TestingPlan).where(*cond)
    stmt = apply_sort(
        stmt, TestingPlan, sort, order,
        {"id", "system_name", "plan_name", "test_type", "department", "status", "est_mandays",
         "actual_mandays", "receive_time", "ticket_seq", "first_test_done_time", "retest_done_time",
         "create_time"},
        (TestingPlan.receive_time.desc(), TestingPlan.ticket_seq.desc(), TestingPlan.id.desc()),
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
    first_test_from: str = "",
    first_test_to: str = "",
    filters: str = "",
    pending: bool = False,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """测试计划多维度统计：总数/复测完成数/初测次数/复测次数/总测试次数/状态分布/按月漏洞数。"""
    cond = plan_query.plan_conditions(
        search, status, test_type, department, receive_from, receive_to,
        first_test_from=first_test_from, first_test_to=first_test_to, pending=pending,
    )
    cond += plan_query.plan_filters_condition(filters)
    return await plan_query.compute_plan_stats(session, cond, receive_from, receive_to)


@router.get("/testing-plans/export")
async def export_testing_plans(
    search: str = "",
    status: int | None = None,
    test_type: str = "",
    department: str = "",
    receive_from: str = "",
    receive_to: str = "",
    first_test_from: str = "",
    first_test_to: str = "",
    filters: str = "",
    pending: bool = False,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """导出筛选后的渗透测试工单明细与统计汇总（双 sheet Excel）。"""
    cond = plan_query.plan_conditions(
        search, status, test_type, department, receive_from, receive_to,
        first_test_from=first_test_from, first_test_to=first_test_to, pending=pending,
    )
    cond += plan_query.plan_filters_condition(filters)
    plans = (
        await session.execute(select(TestingPlan).where(*cond).order_by(TestingPlan.id))
    ).scalars().all()
    stats = await plan_query.compute_plan_stats(session, cond, receive_from, receive_to)
    wb = plan_io.build_export_workbook(plans, stats)
    return xlsx_response(wb, "渗透测试工单导出.xlsx")


@router.get("/testing-plans/conclusion")
async def testing_plan_conclusion(
    search: str = "",
    status: int | None = None,
    test_type: str = "",
    department: str = "",
    receive_from: str = "",
    receive_to: str = "",
    first_test_from: str = "",
    first_test_to: str = "",
    filters: str = "",
    pending: bool = False,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """结论性输出：按筛选条件生成结论文字与附件行数据（部门/系统/漏洞/整改状态聚合）。"""
    cond = plan_query.plan_conditions(
        search, status, test_type, department, receive_from, receive_to,
        first_test_from=first_test_from, first_test_to=first_test_to, pending=pending,
    )
    cond += plan_query.plan_filters_condition(filters)
    return await plan_query.compute_conclusion(session, cond)


@router.get("/testing-plans/conclusion/export")
async def export_testing_plan_conclusion(
    search: str = "",
    status: int | None = None,
    test_type: str = "",
    department: str = "",
    receive_from: str = "",
    receive_to: str = "",
    first_test_from: str = "",
    first_test_to: str = "",
    filters: str = "",
    pending: bool = False,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """下载结论性输出附件（工单ID/所属部门/测试系统/漏洞数/测试类型/整改完成情况）。"""
    cond = plan_query.plan_conditions(
        search, status, test_type, department, receive_from, receive_to,
        first_test_from=first_test_from, first_test_to=first_test_to, pending=pending,
    )
    cond += plan_query.plan_filters_condition(filters)
    data = await plan_query.compute_conclusion(session, cond)
    wb = plan_io.build_conclusion_workbook(data["rows"])
    return xlsx_response(wb, "整改情况附件.xlsx")


@router.get("/testing-plans/import/template")
async def download_plan_import_template(_: User = Depends(require_perm("special:manage"))):
    """下载测试计划导入模板（列与导出一致，ID 留空则新增）。"""
    return xlsx_response(plan_io.build_template_workbook(), "渗透测试工单导入模板.xlsx")


@router.post("/testing-plans/import")
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
    try:
        wb = load_workbook(BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "Excel 文件解析失败，请使用导入模板")
    return await plan_io.upsert_plans(session, wb, user)


# 注意：需注册在 /testing-plans/stats、/testing-plans/export、/testing-plans/import/template 等静态路径之后，防止路径吞噬
@router.get("/testing-plans/{row_id}", response_model=TestingPlanOut)
async def get_testing_plan(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """单条计划详情（含测试人员/关联漏洞/关联报告/复测轮次），供流程抽屉刷新。"""
    return await get_or_404(session, TestingPlan, row_id, "渗透测试工单不存在")


async def _assign_ticket_seq(session: AsyncSession, row: TestingPlan) -> None:
    """按需求接收日期分配当日「最大编号+1」的录入次序（ticket_seq）。

    委托给 ticket_service.assign_ticket_seq：与测试计划同源的工单ID分配逻辑，
    现为测试计划 / 漏扫基线工单两表共享同一当日序号序列（见 services/ticket_service.py）。
    """
    await ticket_service.assign_ticket_seq(session, row)


async def _check_ticket_id_unique(
    session: AsyncSession, ticket_id: str, exclude_id: int | None = None,
    linked_nonpen_ids: list[int] | None = None,
) -> None:
    """校验工单ID唯一性：与「显示编号」口径一致——手动指定值本身，或纯自动记录
    （ticket_id_manual 为空）由 receive_time+ticket_seq 生成的值，均不得与其他记录重复。

    委托给 ticket_service.check_ticket_id_unique：现为测试计划 / 漏扫基线工单两表全局唯一。
    排除自身及联动创建的非渗透记录（联动双方共享同一工单ID，须相互排除）。
    """
    excludes = [(TestingPlan, exclude_id)] if exclude_id is not None else []
    for nid in (linked_nonpen_ids or []):
        excludes.append((NonpenPlan, nid))
    await ticket_service.check_ticket_id_unique(
        session, ticket_id, exclude=excludes or None,
    )


@router.post("/testing-plans", response_model=TestingPlanOut)
async def create_testing_plan(
    body: TestingPlanIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    data = body.model_dump()
    create_nonpen = bool(data.pop("create_nonpen", False))
    nonpen_test_items = list(data.pop("nonpen_test_items") or [])
    row = TestingPlan(**data, creator_id=user.id)
    await _assign_ticket_seq(session, row)
    await _check_ticket_id_unique(session, row.ticket_id)
    session.add(row)
    # 勾选「创建漏扫基线工单」：同一工单联动生成漏扫基线工单（共享工单ID与接收日期）
    if create_nonpen:
        if not nonpen_test_items:
            raise HTTPException(400, "已勾选「创建漏扫基线工单」，请至少选择一个非渗透测试项")
        for k in nonpen_test_items:
            if k not in NONPEN_ITEMS:
                raise HTTPException(400, f"不支持的测试项：{k}")
        if not row.receive_time and not row.ticket_id_manual:
            raise HTTPException(400, "已勾选「创建漏扫基线工单」，请填写「需求接收日期」（用于生成共享工单ID）或手动指定工单ID")
        await session.flush()  # 先持久化测试计划拿到 id，供非渗透记录引用
        session.add(NonpenPlan(
            plan_name=row.plan_name,
            system_name=row.system_name,
            test_type=row.test_type,
            department=row.department,
            ticket_time=row.ticket_time,
            receive_time=row.receive_time,
            ticket_seq=row.ticket_seq,  # 混合工单：非渗透复用测试计划的当日序号
            ticket_id_manual=row.ticket_id_manual,
            asset_ids=list(row.asset_ids or []),
            items=nonpen_service.build_items(nonpen_test_items),
            testing_plan_id=row.id,  # 标记联动来源，用于双向同步与级联删除
            detail=row.detail,
            creator_id=user.id,
        ))
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/testing-plans/{row_id}/claim", response_model=TestingPlanOut)
async def claim_testing_plan(
    row_id: int,
    request: Request,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """认领测试计划：当前用户加入测试人员（幂等）；未测试状态自动进入初测中。"""
    row = await get_or_404(session, TestingPlan, row_id, "渗透测试工单不存在")
    if all(u.id != user.id for u in row.testers):
        row.testers.append(user)
    if row.status == 10:
        row.status = 20
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "plan_claim", user, {
        "target": f"testing-plans/{row_id}", "system": row.system_name,
    })
    await notify(request.app, session, "plan_claimed",
                 system=row.system_name, operator=user.realname or user.username)
    return row


@router.post("/testing-plans/{row_id}/quit", response_model=TestingPlanOut)
async def quit_testing_plan(
    row_id: int,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """退出认领：当前用户移出测试人员列表。"""
    row = await get_or_404(session, TestingPlan, row_id, "渗透测试工单不存在")
    row.testers = [u for u in row.testers if u.id != user.id]
    await session.commit()
    await session.refresh(row)
    return row


def _no_vul_section_html(system_name: str, conclusion: str) -> str:
    """无漏洞报告的「测试结论」章节 HTML（供报告编辑器继续编辑与 Word 导出）。"""
    parts = [
        "<p><strong>测试状态：</strong>初测</p>",
        "<p><strong>测试结论：</strong>经本次安全测试，"
        f"未发现{html_mod.escape(system_name or '被测系统')}存在安全漏洞，安全测试通过。</p>",
    ]
    if conclusion.strip():
        escaped = "<br/>".join(
            html_mod.escape(line) for line in conclusion.strip().splitlines()
        )
        parts.append(f"<p><strong>补充说明：</strong></p><p>{escaped}</p>")
    return "".join(parts)


async def _create_no_vul_report(
    session: AsyncSession, plan: TestingPlan, user: User, title: str, conclusion: str,
) -> Report:
    """为无漏洞计划生成「安全测试通过」报告草稿：单章节测试结论，无漏洞关联。

    标题同计划范围内查重，重复时自动追加「-1」「-2」后缀；测试周期默认取
    需求接收日期至确认当天（未填接收日期时取当天），实际人天自动计算。
    标题不含「复测」，按初测报告口径计入计划实际人天。
    """
    today = tznow().date().isoformat()
    candidate = title
    suffix = 0
    while (
        await session.execute(
            select(Report.id).where(
                Report.title == candidate, Report.testing_plan_id == plan.id
            ).limit(1)
        )
    ).scalar_one_or_none() is not None:
        suffix += 1
        candidate = f"{title}-{suffix}"
    test_start = plan.receive_time or today
    report = Report(
        title=candidate,
        project_name=plan.system_name,
        author=user.realname or user.username,
        test_start=test_start,
        test_end=today,
        status="draft",
        testing_plan_id=plan.id,
        creator_id=user.id,
    )
    report.sections.append(ReportSection(
        order=0, title="测试结论",
        content_html=_no_vul_section_html(plan.system_name, conclusion),
    ))
    session.add(report)
    await session.flush()
    report.actual_mandays = mandays_between(report.test_start, report.test_end)
    return report


@router.post("/testing-plans/{row_id}/complete-no-vuln", response_model=TestingPlanOut)
async def complete_plan_no_vuln(
    row_id: int,
    body: CompleteNoVulnIn,
    request: Request,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """无漏洞闭环：测试完成且确认未发现安全漏洞时，计划直接流转为「测试通过」。

    - 前置校验：计划无关联漏洞（有漏洞须走整改/复测链路）、状态允许流转且未重复确认；
    - 数据记录：状态置为测试通过、初测完成时间打点、记录无漏洞测试结论；
    - 报告归档：默认同步生成「未发现安全漏洞」报告草稿（可导出 Word/PDF 归档）；
    - 通知：站内信告知测试人员与计划创建人；
    - 后续若补录/关联新漏洞，计划自动重开为「初测中」（见 reopen_passed_plan）。
    """
    plan = await get_or_404(session, TestingPlan, row_id, "渗透测试工单不存在")
    if not plan_service.can_operate(user, plan):
        raise HTTPException(403, "仅认领者或管理员可确认无漏洞完结")
    if plan.status == PlanStatus.PASSED:
        raise HTTPException(400, "该计划已确认无漏洞（测试通过），无需重复操作")
    if not vuln_service.can_plan_transition(plan.status, PlanStatus.PASSED):
        raise HTTPException(400, "当前状态不允许确认无漏洞完结")
    vul_count = (
        await session.execute(
            select(func.count(Vul.id)).where(Vul.testing_plan_id == row_id)
        )
    ).scalar_one()
    if vul_count:
        raise HTTPException(400, "该计划存在关联漏洞，不能确认无漏洞，请先处理漏洞后走复测流程")

    # 状态流转与数据记录
    plan.status = PlanStatus.PASSED
    plan.no_vul_conclusion = body.conclusion.strip()
    if not plan.first_test_done_time:
        plan.first_test_done_time = tznow().date().isoformat()

    # 报告归档：生成无漏洞报告草稿（标题不含「复测」，计入计划实际人天）
    report: Report | None = None
    if body.generate_report:
        title = body.title.strip() or (
            f"{tznow().date().strftime('%Y%m%d')}{plan.system_name}渗透测试报告（无漏洞）"
        )
        report = await _create_no_vul_report(session, plan, user, title, body.conclusion)
        # 计划的 reports 关系在创建报告前已预加载，需重新加载后再重算实际人天，避免遍历时漏掉新报告
        await session.refresh(plan, attribute_names=["reports"])
        await plan_service.refresh_mandays(session, plan.id)

    # 站内信通知：测试人员与计划创建人（去重，排除操作人本人）
    notice_ids = {u.id for u in plan.testers}
    if plan.creator_id:
        notice_ids.add(plan.creator_id)
    notice_ids.discard(user.id)
    report_hint = f"，已生成报告《{report.title}》" if report is not None else ""
    for uid in notice_ids:
        session.add(Message(
            user_id=uid,
            msg_type="plan",
            title=f"测试计划「{plan.system_name}」已确认无漏洞",
            content=(
                f"{user.realname or user.username} 确认该计划测试完成且未发现安全漏洞，"
                f"状态流转为「测试通过」{report_hint}"
            ),
        ))
    await session.commit()
    await session.refresh(plan)
    await audit(session, request, "plan_transition", user, {
        "target": f"testing-plans/{row_id}", "system": plan.system_name,
        "to": TESTING_PLAN_STATUS.get(PlanStatus.PASSED, "测试通过"), "no_vuln": True,
    })
    return plan


@router.post("/testing-plans/{row_id}/attach-vulns", response_model=TestingPlanOut)
async def attach_vulns_to_plan(
    row_id: int,
    body: dict,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """从漏洞库批量关联漏洞到当前测试计划（需求1）。

    属录入漏洞阶段：仅已认领该计划的账号可操作（管理员未认领不放行）；
    已关联其他计划的漏洞会被转移至当前计划。
    """
    row = await get_or_404(session, TestingPlan, row_id, "渗透测试工单不存在")
    if not plan_service.is_plan_claimant(user, row):
        raise HTTPException(403, "仅已认领该测试计划的账号可关联漏洞")
    vul_ids = [int(i) for i in (body.get("vul_ids") or [])]
    if not vul_ids:
        raise HTTPException(400, "请选择要关联的漏洞")
    vulns = await vuln_service.load_vulns_or_400(session, vul_ids)
    for v in vulns:
        v.testing_plan_id = row_id
        v.source = 0  # 关联渗透测试工单后漏洞来源固定为「渗透测试工单」（展示层派生）
    # 已确认无漏洞（测试通过）的计划重新关联到漏洞时自动重开为「初测中」
    await plan_service.reopen_passed_plan(session, row_id)
    await plan_service.refresh_stats(session, row_id)
    await session.commit()
    await session.refresh(row)
    return row


@router.put("/testing-plans/{row_id}", response_model=TestingPlanOut)
async def update_testing_plan(
    row_id: int,
    body: TestingPlanIn,
    request: Request,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, TestingPlan, row_id, "渗透测试工单不存在")
    old_status = row.status
    if body.status != row.status and not plan_service.can_operate(user, row):
        raise HTTPException(403, "仅认领者或管理员可修改测试状态")
    # 校验状态流转合法性（仅当状态有变化时）
    if body.status != row.status and not vuln_service.can_plan_transition(row.status, body.status):
        raise HTTPException(400, f"不允许从当前状态流转到目标状态")
    # 编辑页直接流转为「测试通过」时，同样要求计划无关联漏洞（与无漏洞完结接口口径一致）
    if body.status == PlanStatus.PASSED and row.status != PlanStatus.PASSED:
        vul_count = (
            await session.execute(
                select(func.count(Vul.id)).where(Vul.testing_plan_id == row_id)
            )
        ).scalar_one()
        if vul_count:
            raise HTTPException(400, "该计划存在关联漏洞，不能流转为「测试通过」")
    # 手动流转到「复测中」时记一轮复测（已有进行中轮次则不重复计数）
    if body.status == 50 and row.status != 50:
        plan_service.start_retest_round(session, row, "手动流转至复测中", user.id)
    data = body.model_dump()
    # 联动相关字段仅创建时生效：编辑不回写 create_nonpen 勾选，也不存在 nonpen_test_items 列
    data.pop("create_nonpen", None)
    data.pop("nonpen_test_items", None)
    for k, v in data.items():
        setattr(row, k, v)
    # 补生成工单ID序号（历史/导入数据无序号时自动补齐）
    await _assign_ticket_seq(session, row)
    # 联动漏扫基线工单：编辑测试计划公共字段时双向同步；联动双方共享同一工单ID，唯一性校验需相互排除
    linked = (await session.execute(
        select(NonpenPlan).where(NonpenPlan.testing_plan_id == row.id)
    )).scalars().all()
    # 保存前校验工单ID唯一性（手动指定值或自动生成值均不可重复）
    await _check_ticket_id_unique(
        session, row.ticket_id, exclude_id=row.id,
        linked_nonpen_ids=[np.id for np in linked],
    )
    # 有关联漏洞时统计以自动重算为准，覆盖手填值
    if row.vuls:
        await plan_service.refresh_stats(session, row.id)
    # 有关联初测报告时实际人天自动计算（仅纳入初测报告，复测报告不计入）
    await plan_service.refresh_mandays(session, row.id)
    # 联动双向同步：编辑测试计划公共字段时，自动同步更新其联动的漏扫基线工单
    for np in linked:
        nonpen_service.sync_linked_fields(row, np)
    await session.commit()
    await session.refresh(row)
    if body.status != old_status:
        await audit(session, request, "plan_transition", user, {
            "target": f"testing-plans/{row_id}", "system": row.system_name,
            "from": TESTING_PLAN_STATUS.get(old_status, str(old_status)),
            "to": TESTING_PLAN_STATUS.get(body.status, str(body.status)),
        })
    return row


@router.delete("/testing-plans/{row_id}")
async def delete_testing_plan(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(TestingPlan, row_id)
    if row:
        # 级联删除联动创建的漏扫基线工单（联动双向：删除任一方，另一方同步删除）
        linked = (await session.execute(
            select(NonpenPlan).where(NonpenPlan.testing_plan_id == row_id)
        )).scalars().all()
        for np in linked:
            await session.delete(np)
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
