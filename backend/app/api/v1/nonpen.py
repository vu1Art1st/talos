"""漏扫基线工单 API：主机/Web/基线扫描类测试的独立管理，与测试计划平级（统一 special:manage 权限）。

- 工单ID与测试计划共享同一当日序号序列（ticket_service.assign_ticket_seq）；
- 测试项（baseline/host/web）独立流转，状态与次数存于 items JSON 容器；
- testing_plan_id 非空表示由测试计划联动创建：编辑公共字段双向同步，删除互相级联；
- 不关联漏洞 / 报告 / 人天，保持扫描类业务逻辑独立（需求确认）。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
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
from app.services import nonpen_service, plan_crud, plan_query

router = APIRouter(tags=["漏扫基线工单"])


# 注意：/nonpen-plans/stats 需注册在 /nonpen-plans/{row_id} 之前，防止路径吞噬
@router.get("/nonpen-plans/stats")
async def nonpen_plan_stats(
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """漏扫基线工单统计（五张卡片）：总数 / 复测完成 / 基线扫描次数 / 主机扫描次数 / Web扫描次数。"""
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
        cond.append(plan_query.nonpen_search_condition(search))
    stmt = select(NonpenPlan).where(*cond)
    stmt = apply_sort(
        stmt, NonpenPlan, sort, order,
        {"id", "plan_name", "system_name", "test_type", "department",
         "receive_time", "ticket_time", "ticket_seq", "create_time"},
        (NonpenPlan.receive_time.desc(), NonpenPlan.ticket_seq.desc(), NonpenPlan.id.desc()),
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
    return await plan_crud.create_nonpen(session, body.model_dump(), user)


@router.get("/nonpen-plans/{row_id}", response_model=NonpenPlanOut)
async def get_nonpen_plan(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """单条漏扫基线工单详情（含测试项状态容器），供流程抽屉刷新。"""
    return await get_or_404(session, NonpenPlan, row_id, "漏扫基线工单不存在")


@router.put("/nonpen-plans/{row_id}", response_model=NonpenPlanOut)
async def update_nonpen_plan(
    row_id: int,
    body: NonpenPlanIn,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, NonpenPlan, row_id, "漏扫基线工单不存在")
    return await plan_crud.update_nonpen(session, row, body.model_dump())


@router.delete("/nonpen-plans/{row_id}")
async def delete_nonpen_plan(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(NonpenPlan, row_id)
    if row:
        # 联动双向：删除联动的漏扫基线工单时，级联删除其来源测试计划（含漏洞/报告解除关联）
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
    row = await get_or_404(session, NonpenPlan, row_id, "漏扫基线工单不存在")
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
    row = await get_or_404(session, NonpenPlan, row_id, "漏扫基线工单不存在")
    nonpen_service.apply_item_action(row, item_key, "ignore" if body.ignored else "unignore")
    await session.commit()
    await session.refresh(row)
    return row
