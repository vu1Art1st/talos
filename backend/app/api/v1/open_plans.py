"""开放 API 工单部分（F6 扩展 + P1-6 成熟化）：渗透测试工单与漏扫基线工单的查询 / 创建 / 更新。

设计口径（与 /open/vulns、/open/stats 保持一致）：

- 认证：仅个人访问令牌 PAT（`core/deps.get_pat_user`），JWT 会话令牌被拒；
- scope（P1-6）：读接口接受全部 scope；写接口要求 `plan_write` / `full`，
  只读令牌无法写（`core/deps.require_pat_perm`）；
- 读：复用站内筛选构造器 `plan_query.plan_conditions`，口径与站内列表一致；
  不做数据归属过滤（PAT 可读取全量工单），与既有开放接口一致；
- 写：按令牌所属用户的角色权限校验 `special:manage`（与站内 `require_perm` 同口径），
  并支持 `Idempotency-Key`（重复提交返回首次结果，同键不同内容 409）；
- 分页：默认 `page`/`size`；传 `cursor` 时按 id 降序稳定遍历并返回 `next_cursor`；
- 写入逻辑复用 `services.plan_crud`（与站内路由同一实现），保证工单ID分配、
  状态流转校验、联动同步与统计重算口径不漂移。
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import TESTING_PLAN_STATUS
from app.core.deps import require_pat_perm, require_pat_read
from app.core.query import apply_sort, get_or_404, paginate_cursor
from app.db import get_session
from app.models import NonpenPlan, TestingPlan, User
from app.schemas import (
    NonpenPlanIn,
    NonpenPlanOut,
    Page,
    TestingPlanIn,
    TestingPlanOut,
)
from app.services import idempotency, plan_crud, plan_query, stats_cache
from app.services.audit_service import audit

router = APIRouter(prefix="/open", tags=["开放API-工单"])

# 排序白名单与默认次序：与站内工单列表保持一致（需求接收日期倒序 → 当日序号倒序 → ID 倒序）
PLAN_SORT_FIELDS = {
    "id", "system_name", "plan_name", "test_type", "department", "status", "est_mandays",
    "actual_mandays", "receive_time", "ticket_seq", "first_test_done_time",
    "retest_done_time", "create_time",
}
PLAN_DEFAULT_ORDER = (
    TestingPlan.receive_time.desc(), TestingPlan.ticket_seq.desc(), TestingPlan.id.desc(),
)
NONPEN_SORT_FIELDS = {
    "id", "plan_name", "system_name", "test_type", "department",
    "receive_time", "ticket_time", "ticket_seq", "create_time",
}
NONPEN_DEFAULT_ORDER = (
    NonpenPlan.receive_time.desc(), NonpenPlan.ticket_seq.desc(), NonpenPlan.id.desc(),
)


async def _idem_begin(request: Request, session: AsyncSession, user: User, endpoint: str, payload):
    """写操作幂等前置（P1-6）：返回 `(需直接返回的响应 | None, 幂等键)`。"""
    key = idempotency.key_of(request.headers)
    if not key:
        return None, ""
    outcome, replay = await idempotency.claim(session, user.id, endpoint, key, payload)
    if outcome == "conflict":
        raise HTTPException(409, "Idempotency-Key 已用于不同的请求内容，请更换幂等键")
    if outcome == "replay" and replay:
        return JSONResponse(content=replay["response"], status_code=replay["status_code"]), key
    return None, key


# ---------- 渗透测试工单 ----------
@router.get("/testing-plans", response_model=Page[TestingPlanOut])
async def open_list_testing_plans(
    search: str = "",
    status: int | None = None,
    test_type: str = "",
    department: str = "",
    receive_from: str = "",
    receive_to: str = "",
    first_test_from: str = "",
    first_test_to: str = "",
    sort: str = "",
    order: str = "desc",
    cursor: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_pat_read),
    session: AsyncSession = Depends(get_session),
):
    """渗透测试工单分页列表（筛选参数与站内 GET /testing-plans 的固定参数一致）。

    search 匹配测试系统 / 所属部门 / 测试类型 / 工单ID；时间参数为 YYYY-MM-DD 闭区间。
    """
    cond = plan_query.plan_conditions(
        search, status, test_type, department, receive_from, receive_to,
        first_test_from=first_test_from, first_test_to=first_test_to,
    )
    stmt = apply_sort(
        select(TestingPlan).where(*cond), TestingPlan, sort, order,
        PLAN_SORT_FIELDS, PLAN_DEFAULT_ORDER,
    )
    total, items, meta = await paginate_cursor(
        session, stmt, page=page, size=size, cursor=cursor, id_col=TestingPlan.id,
    )
    return Page(total=total, items=items, **meta)


@router.get("/testing-plans/{row_id}", response_model=TestingPlanOut)
async def open_get_testing_plan(
    row_id: int,
    _: User = Depends(require_pat_read),
    session: AsyncSession = Depends(get_session),
):
    """单条渗透测试工单详情（含测试人员 / 关联漏洞 / 关联报告 / 复测轮次）。"""
    return await get_or_404(session, TestingPlan, row_id, "渗透测试工单不存在")


@router.post("/testing-plans", response_model=TestingPlanOut)
async def open_create_testing_plan(
    body: TestingPlanIn,
    request: Request,
    user: User = Depends(require_pat_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """创建渗透测试工单（工单ID自动分配或手动指定；可勾选联动生成漏扫基线工单）。

    支持 `Idempotency-Key`：同键重放返回首次创建的工单，不再产生第二个工单。
    """
    early, idem_key = await _idem_begin(
        request, session, user, "POST /open/testing-plans", body.model_dump(),
    )
    if early is not None:
        return early
    row = await plan_crud.create_plan(session, body.model_dump(), user)
    await audit(session, request, "plan_create", user, {
        "target": f"testing-plans/{row.id}", "system": row.system_name,
        "ticket_id": row.ticket_id, "source": "开放API",
    })
    out = TestingPlanOut.model_validate(row)
    if idem_key:
        await idempotency.remember(
            session, user.id, "POST /open/testing-plans", idem_key, 200, out,
        )
    stats_cache.invalidate()
    return out


@router.put("/testing-plans/{row_id}", response_model=TestingPlanOut)
async def open_update_testing_plan(
    row_id: int,
    body: TestingPlanIn,
    request: Request,
    user: User = Depends(require_pat_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """全量更新渗透测试工单（PUT，请求体与创建一致；状态流转受状态机与认领关系约束）。"""
    endpoint = f"PUT /open/testing-plans/{row_id}"
    early, idem_key = await _idem_begin(
        request, session, user, endpoint, body.model_dump(),
    )
    if early is not None:
        return early
    row = await get_or_404(session, TestingPlan, row_id, "渗透测试工单不存在")
    row, old_status = await plan_crud.update_plan(session, row, body.model_dump(), user)
    if body.status != old_status:
        await audit(session, request, "plan_transition", user, {
            "target": f"testing-plans/{row.id}", "system": row.system_name,
            "from": TESTING_PLAN_STATUS.get(old_status, str(old_status)),
            "to": TESTING_PLAN_STATUS.get(body.status, str(body.status)),
            "source": "开放API",
        })
    await audit(session, request, "plan_update", user, {
        "target": f"testing-plans/{row.id}", "system": row.system_name,
        "ticket_id": row.ticket_id, "source": "开放API",
    })
    out = TestingPlanOut.model_validate(row)
    if idem_key:
        await idempotency.remember(session, user.id, endpoint, idem_key, 200, out)
    stats_cache.invalidate()
    return out


# ---------- 漏扫基线工单 ----------
@router.get("/nonpen-plans", response_model=Page[NonpenPlanOut])
async def open_list_nonpen_plans(
    search: str = "",
    actionable: bool = False,  # true=仅返回存在非忽略测试项处于可测试状态的工单
    sort: str = "",
    order: str = "desc",
    cursor: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_pat_read),
    session: AsyncSession = Depends(get_session),
):
    """漏扫基线工单分页列表（search 匹配计划名称 / 测试系统 / 部门 / 工单ID）。

    「仅可进行」与站内同口径，统一由 `plan_query.nonpen_actionable_condition` 下推到 SQL
    （P0-4）：不再「取回最多 10000 条后在应用层过滤再分页」。
    """
    cond = [plan_query.nonpen_search_condition(search)] if search else []
    if actionable:
        cond.append(plan_query.nonpen_actionable_condition())
    stmt = apply_sort(
        select(NonpenPlan).where(*cond), NonpenPlan, sort, order,
        NONPEN_SORT_FIELDS, NONPEN_DEFAULT_ORDER,
    )
    total, items, meta = await paginate_cursor(
        session, stmt, page=page, size=size, cursor=cursor, id_col=NonpenPlan.id,
    )
    return Page(total=total, items=items, **meta)


@router.get("/nonpen-plans/{row_id}", response_model=NonpenPlanOut)
async def open_get_nonpen_plan(
    row_id: int,
    _: User = Depends(require_pat_read),
    session: AsyncSession = Depends(get_session),
):
    """单条漏扫基线工单详情（含 items 测试项状态容器）。"""
    return await get_or_404(session, NonpenPlan, row_id, "漏扫基线工单不存在")


@router.post("/nonpen-plans", response_model=NonpenPlanOut)
async def open_create_nonpen_plan(
    body: NonpenPlanIn,
    request: Request,
    user: User = Depends(require_pat_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """创建漏扫基线工单：工单ID 与渗透测试工单共享当日序号序列，测试项按勾选初始化。"""
    early, idem_key = await _idem_begin(
        request, session, user, "POST /open/nonpen-plans", body.model_dump(),
    )
    if early is not None:
        return early
    row = await plan_crud.create_nonpen(session, body.model_dump(), user)
    await audit(session, request, "plan_create", user, {
        "target": f"nonpen-plans/{row.id}", "system": row.system_name,
        "ticket_id": row.ticket_id, "source": "开放API",
    })
    out = NonpenPlanOut.model_validate(row)
    if idem_key:
        await idempotency.remember(session, user.id, "POST /open/nonpen-plans", idem_key, 200, out)
    stats_cache.invalidate()
    return out


@router.put("/nonpen-plans/{row_id}", response_model=NonpenPlanOut)
async def open_update_nonpen_plan(
    row_id: int,
    body: NonpenPlanIn,
    request: Request,
    user: User = Depends(require_pat_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    """全量更新漏扫基线工单：仅合并测试项勾选变化，保留未变化项的状态与扫描次数。"""
    endpoint = f"PUT /open/nonpen-plans/{row_id}"
    early, idem_key = await _idem_begin(request, session, user, endpoint, body.model_dump())
    if early is not None:
        return early
    row = await get_or_404(session, NonpenPlan, row_id, "漏扫基线工单不存在")
    row = await plan_crud.update_nonpen(session, row, body.model_dump())
    await audit(session, request, "plan_update", user, {
        "target": f"nonpen-plans/{row.id}", "system": row.system_name,
        "ticket_id": row.ticket_id, "source": "开放API",
    })
    out = NonpenPlanOut.model_validate(row)
    if idem_key:
        await idempotency.remember(session, user.id, endpoint, idem_key, 200, out)
    stats_cache.invalidate()
    return out
