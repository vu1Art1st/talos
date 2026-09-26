"""漏扫基线工单 API：主机/Web/基线扫描类测试的独立管理，与测试计划平级（统一 special:manage 权限）。

- 工单ID与测试计划共享同一当日序号序列（ticket_service.assign_ticket_seq）；
- 测试项（baseline/host/web）独立流转，状态与次数存于 items JSON 容器；
- testing_plan_id 非空表示由测试计划联动创建：编辑公共字段双向同步，删除互相级联；
- 不关联漏洞 / 报告 / 人天，保持扫描类业务逻辑独立（需求确认）。
"""
from fastapi import APIRouter, Depends, Query
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


# 输出组装（必须定义在路由装饰器之前，否则装饰器会绑到辅助函数上、路由静默消失）
async def _out(session: AsyncSession, row: NonpenPlan) -> NonpenPlanOut:
    """单条输出：补齐关联资产名称（`NonpenPlanOut.asset_names`，2026-09-22 契约检查发现缺失）。"""
    return nonpen_service.to_out(row, await nonpen_service.asset_name_map(session, [row]))


async def _out_many(session: AsyncSession, rows: list[NonpenPlan]) -> list[NonpenPlanOut]:
    """批量输出：一次查询解析全部行的关联资产名称（列表分页也仅多一次 SQL）。"""
    names = await nonpen_service.asset_name_map(session, rows)
    return [nonpen_service.to_out(row, names) for row in rows]


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
    # 「仅可进行」下推到 SQL（P0-4）：不再取回全量后在应用层过滤再分页
    if actionable:
        cond.append(plan_query.nonpen_actionable_condition())
    stmt = select(NonpenPlan).where(*cond)
    stmt = apply_sort(
        stmt, NonpenPlan, sort, order,
        {"id", "plan_name", "system_name", "test_type", "department",
         "receive_time", "ticket_time", "ticket_seq", "create_time"},
        (NonpenPlan.receive_time.desc(), NonpenPlan.ticket_seq.desc(), NonpenPlan.id.desc()),
    )
    total, items = await paginate(session, stmt, page, size)
    return Page(total=total, items=await _out_many(session, items))


@router.post("/nonpen-plans", response_model=NonpenPlanOut)
async def create_nonpen_plan(
    body: NonpenPlanIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await plan_crud.create_nonpen(session, body.model_dump(), user)
    return await _out(session, row)


@router.get("/nonpen-plans/{row_id}", response_model=NonpenPlanOut)
async def get_nonpen_plan(
    row_id: int,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """单条漏扫基线工单详情（含测试项状态容器），供流程抽屉刷新。"""
    row = await get_or_404(session, NonpenPlan, row_id, "漏扫基线工单不存在")
    return await _out(session, row)


@router.put("/nonpen-plans/{row_id}", response_model=NonpenPlanOut)
async def update_nonpen_plan(
    row_id: int,
    body: NonpenPlanIn,
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = await get_or_404(session, NonpenPlan, row_id, "漏扫基线工单不存在")
    updated = await plan_crud.update_nonpen(session, row, body.model_dump())
    return await _out(session, updated)


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
    return await _out(session, row)


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
    return await _out(session, row)
