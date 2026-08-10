"""非渗透计划 API：主机/Web/基线扫描类测试的独立管理，与测试计划平级（统一 special:manage 权限）。

- 工单ID与测试计划共享同一当日序号序列（ticket_service.assign_ticket_seq）；
- 测试项（baseline/host/web）独立流转，状态与次数存于 items JSON 容器；
- testing_plan_id 非空表示由测试计划联动创建：编辑公共字段双向同步，删除互相级联；
- 不关联漏洞 / 报告 / 人天，保持扫描类业务逻辑独立（需求确认）。
"""
import re

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.core.query import apply_sort, get_or_404, paginate
from app.db import get_session
from app.models import NonpenPlan, Report, TestingPlan, User, Vul
from app.schemas import (
    NonpenItemIgnoreIn,
    NonpenItemTransitionIn,
    NonpenPlanIn,
    NonpenPlanOut,
    Page,
)
from app.services import nonpen_service, ticket_service

router = APIRouter(tags=["非渗透计划"])


def _search_condition(search: str):
    """搜索：计划名称 / 测试系统 / 所属部门 / 工单ID（手动指定值，或 YYYYMMDD-N 自动编号的日期+序号组合）。"""
    pat = f"%{search}%"
    conds = [
        NonpenPlan.plan_name.ilike(pat),
        NonpenPlan.system_name.ilike(pat),
        NonpenPlan.department.ilike(pat),
        NonpenPlan.ticket_id_manual.ilike(pat),
        NonpenPlan.receive_time.ilike(pat),
        func.replace(NonpenPlan.receive_time, "-", "").ilike(pat),
        func.cast(NonpenPlan.ticket_seq, String).ilike(pat),
    ]
    # 完整工单ID匹配：YYYYMMDD-N（如 20260810-3）→ 手动指定值本身，或自动编号的日期+当日序号组合
    m = re.fullmatch(r"(\d{8})-(\d+)", search)
    if m:
        date_like = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}%"
        conds.append(NonpenPlan.receive_time.like(date_like) & (NonpenPlan.ticket_seq == int(m.group(2))))
    return or_(*conds)


# 注意：/nonpen-plans/stats 需注册在 /nonpen-plans/{row_id} 之前，防止路径吞噬
@router.get("/nonpen-plans/stats")
async def nonpen_plan_stats(
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """非渗透计划统计（五张卡片）：总数 / 复测完成 / 基线扫描次数 / 主机扫描次数 / Web扫描次数。"""
    rows = (await session.execute(select(NonpenPlan))).scalars().all()
    return nonpen_service.compute_plan_stats(list(rows))


@router.get("/nonpen-plans", response_model=Page[NonpenPlanOut])
async def list_nonpen_plans(
    search: str = "",
    actionable: bool = False,  # true=仅可进行（存在非忽略测试项处于可测试状态）
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(_search_condition(search))
    stmt = select(NonpenPlan).where(*cond)
    stmt = apply_sort(
        stmt, NonpenPlan, sort, order,
        {"id", "plan_name", "system_name", "test_type", "department",
         "receive_time", "ticket_time", "ticket_seq", "create_time"},
        NonpenPlan.id.desc(),
    )
    # 「仅可进行」依赖 items JSON 的派生判定，SQL 层无法直接过滤，取回后应用层过滤再分页
    total, items = await paginate(session, stmt, 1, 10_000)
    if actionable:
        items = [r for r in items if r.actionable]
    total = len(items)
    items = items[(page - 1) * size: page * size]
    return Page(total=total, items=items)


@router.post("/nonpen-plans", response_model=NonpenPlanOut)
async def create_nonpen_plan(
    body: NonpenPlanIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    data = body.model_dump()
    test_items = list(data.pop("test_items") or [])
    row = NonpenPlan(**data, items=nonpen_service.build_items(test_items), creator_id=user.id)
    await ticket_service.assign_ticket_seq(session, row)
    await ticket_service.check_ticket_id_unique(session, row.ticket_id)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/nonpen-plans/{row_id}", response_model=NonpenPlanOut)
async def get_nonpen_plan(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """单条非渗透计划详情（含测试项状态容器），供流程抽屉刷新。"""
    return await get_or_404(session, NonpenPlan, row_id, "非渗透计划不存在")


@router.put("/nonpen-plans/{row_id}", response_model=NonpenPlanOut)
async def update_nonpen_plan(
    row_id: int,
    body: NonpenPlanIn,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, NonpenPlan, row_id, "非渗透计划不存在")
    data = body.model_dump()
    test_items = list(data.pop("test_items") or [])
    for k, v in data.items():
        setattr(row, k, v)
    # 编辑仅合并勾选变化，保留未变化测试项的状态与次数（不重置）
    row.items = nonpen_service.merge_items(row.items, test_items)
    # 联动双方共享同一工单ID，唯一性校验需排除自身及来源测试计划
    excludes = [(NonpenPlan, row.id)]
    if row.testing_plan_id is not None:
        excludes.append((TestingPlan, row.testing_plan_id))
    await ticket_service.check_ticket_id_unique(session, row.ticket_id, exclude=excludes)
    # 联动双向同步：编辑联动非渗透计划公共字段时，自动同步更新其来源测试计划
    if row.testing_plan_id is not None:
        source = await session.get(TestingPlan, row.testing_plan_id)
        if source is not None:
            nonpen_service.sync_linked_fields(row, source)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete("/nonpen-plans/{row_id}")
async def delete_nonpen_plan(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(NonpenPlan, row_id)
    if row:
        # 联动双向：删除联动的非渗透计划时，级联删除其来源测试计划（含漏洞/报告解除关联）
        if row.testing_plan_id is not None:
            tp = await session.get(TestingPlan, row.testing_plan_id)
            if tp is not None:
                await session.execute(
                    update(Vul).where(Vul.testing_plan_id == tp.id).values(testing_plan_id=None)
                )
                await session.execute(
                    update(Report).where(Report.testing_plan_id == tp.id).values(testing_plan_id=None)
                )
                await session.delete(tp)
        await session.delete(row)
        await session.commit()
    return {"msg": "删除成功"}


@router.post("/nonpen-plans/{row_id}/items/{item_key}/transition", response_model=NonpenPlanOut)
async def nonpen_item_transition(
    row_id: int,
    item_key: str,
    body: NonpenItemTransitionIn,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """测试项状态流转：start / done / direct_done / start_retest / pass / fail / reset，
    按 NONPEN_ITEM_ACTIONS 白名单校验（含次数统计）。"""
    row = await get_or_404(session, NonpenPlan, row_id, "非渗透计划不存在")
    nonpen_service.apply_item_action(row, item_key, body.action)
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/nonpen-plans/{row_id}/items/{item_key}/ignore", response_model=NonpenPlanOut)
async def nonpen_item_ignore(
    row_id: int,
    item_key: str,
    body: NonpenItemIgnoreIn,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """忽略 / 取消忽略测试项：忽略保留次数不参与统计；取消忽略恢复初始状态（次数清零）。"""
    row = await get_or_404(session, NonpenPlan, row_id, "非渗透计划不存在")
    nonpen_service.apply_item_action(row, item_key, "ignore" if body.ignored else "unignore")
    await session.commit()
    await session.refresh(row)
    return row
