"""工单写入逻辑：渗透测试工单 / 漏扫基线工单的创建与更新，站内路由与开放 API 共用。

抽出本模块的原因：开放 API（PAT 认证，见 api/v1/open_plans.py）需要复刻站内工单的
写入语义，若两份实现各自维护会出现口径漂移。以下环节必须保持一致：
    - 工单ID 分配（ticket_service.assign_ticket_seq，两表共享当日序号序列）与唯一性校验；
    - 渗透测试工单的状态流转校验、认领者操作边界、漏洞/人天统计重算；
    - 勾选「创建漏扫基线工单」的联动创建，以及联动双方的公共字段双向同步。
"""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import NONPEN_ITEMS, PlanStatus
from app.models import NonpenPlan, TestingPlan, User, Vul
from app.services import nonpen_service, plan_service, ticket_service, vuln_service


async def create_plan(session: AsyncSession, data: dict, user: User) -> TestingPlan:
    """创建渗透测试工单；勾选 create_nonpen 时联动生成漏扫基线工单（共享工单ID）。"""
    payload = dict(data)
    create_nonpen = bool(payload.pop("create_nonpen", False))
    nonpen_test_items = list(payload.pop("nonpen_test_items") or [])
    row = TestingPlan(**payload, creator_id=user.id)
    await ticket_service.assign_ticket_seq(session, row)
    await ticket_service.check_ticket_id_unique(session, row.ticket_id)
    session.add(row)
    if create_nonpen:
        if not nonpen_test_items:
            raise HTTPException(400, "已勾选「创建漏扫基线工单」，请至少选择一个非渗透测试项")
        for k in nonpen_test_items:
            if k not in NONPEN_ITEMS:
                raise HTTPException(400, f"不支持的测试项：{k}")
        if not row.receive_time and not row.ticket_id_manual:
            raise HTTPException(
                400,
                "已勾选「创建漏扫基线工单」，请填写「需求接收日期」（用于生成共享工单ID）或手动指定工单ID",
            )
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


async def update_plan(
    session: AsyncSession, row: TestingPlan, data: dict, user: User,
) -> tuple[TestingPlan, int]:
    """全量更新渗透测试工单，返回 (工单, 更新前状态) 供调用方按需写审计日志。"""
    old_status = row.status
    new_status = data.get("status", row.status)
    if new_status != row.status and not plan_service.can_operate(user, row):
        raise HTTPException(403, "仅认领者或管理员可修改测试状态")
    if new_status != row.status and not vuln_service.can_plan_transition(row.status, new_status):
        raise HTTPException(400, "不允许从当前状态流转到目标状态")
    # 编辑页直接流转为「测试通过」时，同样要求计划无关联漏洞（与无漏洞完结接口口径一致）
    if new_status == PlanStatus.PASSED and row.status != PlanStatus.PASSED:
        vul_count = (
            await session.execute(
                select(func.count(Vul.id)).where(Vul.testing_plan_id == row.id)
            )
        ).scalar_one()
        if vul_count:
            raise HTTPException(400, "该计划存在关联漏洞，不能流转为「测试通过」")
    # 手动流转到「复测中」时记一轮复测（已有进行中轮次则不重复计数）
    if new_status == 50 and row.status != 50:
        plan_service.start_retest_round(session, row, "手动流转至复测中", user.id)

    payload = dict(data)
    # 联动相关字段仅创建时生效：编辑不回写 create_nonpen 勾选，也不存在 nonpen_test_items 列
    payload.pop("create_nonpen", None)
    payload.pop("nonpen_test_items", None)
    for k, v in payload.items():
        setattr(row, k, v)
    # 补生成工单ID序号（历史/导入数据无序号时自动补齐）
    await ticket_service.assign_ticket_seq(session, row)
    # 联动漏扫基线工单：编辑测试计划公共字段时双向同步；联动双方共享同一工单ID，唯一性校验需相互排除
    linked = (
        await session.execute(select(NonpenPlan).where(NonpenPlan.testing_plan_id == row.id))
    ).scalars().all()
    await ticket_service.check_ticket_id_unique(
        session, row.ticket_id,
        exclude=[(TestingPlan, row.id), *((NonpenPlan, np.id) for np in linked)],
    )
    # 有关联漏洞时统计以自动重算为准，覆盖手填值
    if row.vuls:
        await plan_service.refresh_stats(session, row.id)
    # 有关联初测报告时实际人天自动计算（仅纳入初测报告，复测报告不计入）
    await plan_service.refresh_mandays(session, row.id)
    for np in linked:
        nonpen_service.sync_linked_fields(row, np)
    await session.commit()
    await session.refresh(row)
    return row, old_status


async def create_nonpen(session: AsyncSession, data: dict, user: User) -> NonpenPlan:
    """创建漏扫基线工单：测试项勾选项置 not_started，未勾选项置 ignored（不参与统计）。"""
    payload = dict(data)
    test_items = list(payload.pop("test_items") or [])
    row = NonpenPlan(
        **payload, items=nonpen_service.build_items(test_items), creator_id=user.id,
    )
    await ticket_service.assign_ticket_seq(session, row)
    await ticket_service.check_ticket_id_unique(session, row.ticket_id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_nonpen(session: AsyncSession, row: NonpenPlan, data: dict) -> NonpenPlan:
    """全量更新漏扫基线工单：仅合并测试项勾选变化，保留未变化项的状态与次数。"""
    payload = dict(data)
    test_items = list(payload.pop("test_items") or [])
    for k, v in payload.items():
        setattr(row, k, v)
    row.items = nonpen_service.merge_items(row.items, test_items)
    # 联动双方共享同一工单ID，唯一性校验需排除自身及来源测试计划
    excludes: list[tuple] = [(NonpenPlan, row.id)]
    if row.testing_plan_id is not None:
        excludes.append((TestingPlan, row.testing_plan_id))
    await ticket_service.check_ticket_id_unique(session, row.ticket_id, exclude=excludes)
    # 联动双向同步：编辑联动漏扫基线工单公共字段时，自动同步更新其来源测试计划
    if row.testing_plan_id is not None:
        source = await session.get(TestingPlan, row.testing_plan_id)
        if source is not None:
            nonpen_service.sync_linked_fields(row, source)
    await session.commit()
    await session.refresh(row)
    return row
