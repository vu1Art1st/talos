"""站内通知中心与个人待办工作台（P1-2）。

- `/messages*`：站内消息（分页、按类型筛选、单条/批量已读、未读数）；
- `/todos`：个人待办聚合（原有待办分类 + 已认领的进行中 / 已完成工单）。

消息写入的唯一入口是 `services/message_service.create_message`，本模块只读与置已读。
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import MESSAGE_TYPES, TESTING_PLAN_STATUS, VUL_LEVEL, PlanStatus
from app.core.deps import get_current_user, user_permissions
from app.core.query import paginate
from app.db import get_session
from app.models import ImportBatch, Message, TestingPlan, User, Vul, testing_plan_testers
from app.schemas import (
    MessageOut,
    MessagePage,
    MessageReadIn,
    TodoItemOut,
    TodoItemPageOut,
    TodoSummaryOut,
)
from app.services import sla_service

router = APIRouter(tags=["站内消息与待办"])

# 工作台折叠态每个分类返回的明细条数；展开态走 `/todos/{category}` 分页取全量
_TODO_ITEM_LIMIT = 8

# 工单类待办的深链：`plan` 查询参数由 TestingPlanList 解析并**直接打开该工单的流程抽屉**，
# 只给 `/testing-plans` 会退化为「跳到工单列表页」，故不允许再出现无参数形态。
_PLAN_LINK = "/testing-plans?plan={id}"


# ---------- 站内消息 ----------
@router.get("/messages", response_model=MessagePage)
async def list_messages(
    msg_type: str = "",
    unread_only: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """当前用户的消息分页（按类型筛选 / 仅未读），同时返回未读总数。"""
    cond = [Message.user_id == user.id]
    if msg_type:
        if msg_type not in MESSAGE_TYPES:
            raise HTTPException(400, "未知的消息类型")
        cond.append(Message.msg_type == msg_type)
    if unread_only:
        cond.append(Message.is_read.is_(False))
    total, rows = await paginate(
        session, select(Message).where(*cond).order_by(Message.id.desc()), page, size,
    )
    unread = (
        await session.execute(
            select(func.count(Message.id)).where(
                Message.user_id == user.id, Message.is_read.is_(False)
            )
        )
    ).scalar_one()
    return MessagePage(
        total=total, unread=unread, items=[MessageOut.model_validate(m) for m in rows],
    )


@router.get("/messages/unread-count")
async def unread_count(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """顶栏铃铛徽标：未读数（刷新页面后与服务端一致）。"""
    n = (
        await session.execute(
            select(func.count(Message.id)).where(
                Message.user_id == user.id, Message.is_read.is_(False)
            )
        )
    ).scalar_one()
    return {"unread": n}


@router.post("/messages/{message_id}/read")
async def read_one(
    message_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """单条已读；仅能操作本人消息（越权返回 404，不泄露他人在此 ID 上的消息是否存在）。"""
    row = await session.get(Message, message_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(404, "消息不存在")
    row.is_read = True
    await session.commit()
    return {"msg": "ok"}


@router.post("/messages/read")
async def mark_read(
    body: MessageReadIn | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """批量已读：传入 ids 只置这些消息；不传 / ids 为空则全部已读。"""
    cond = [Message.user_id == user.id]
    ids = (body.ids if body else []) or []
    if ids:
        cond.append(Message.id.in_(ids))
    result = await session.execute(
        update(Message).where(*cond).values(is_read=True)
    )
    await session.commit()
    return {"msg": "ok", "updated": int(result.rowcount or 0)}


# ---------- 个人待办聚合 ----------
def _has(user: User, perm: str) -> bool:
    perms = user_permissions(user)
    return "*" in perms or perm in perms


async def _unclaimed_todos(
    session: AsyncSession, *, offset: int = 0, limit: int = _TODO_ITEM_LIMIT,
) -> TodoItemOut:
    cond = [
        TestingPlan.status == PlanStatus.UNTESTED,
        ~exists().where(testing_plan_testers.c.testing_plan_id == TestingPlan.id),
    ]
    count = (await session.execute(select(func.count(TestingPlan.id)).where(*cond))).scalar_one()
    rows = (
        await session.execute(
            select(TestingPlan)
            .where(*cond)
            .order_by(TestingPlan.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    items = [
        {
            "id": p.id, "ticket_id": p.ticket_id, "system_name": p.system_name,
            "department": p.department, "link": _PLAN_LINK.format(id=p.id),
        }
        for p in rows
    ]
    return TodoItemOut(category="plan_unclaimed", name="待认领工单", count=count, items=items)


async def _my_vuln_todos(
    session: AsyncSession, user: User, *, offset: int = 0, limit: int = _TODO_ITEM_LIMIT,
) -> TodoItemOut:
    stops = [20, 60]
    cond = [Vul.submitter_id == user.id, Vul.status.notin_(stops)]
    count = (await session.execute(select(func.count(Vul.id)).where(*cond))).scalar_one()
    rows = (
        await session.execute(
            select(Vul).where(*cond).order_by(Vul.id.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()
    items = [
        {
            "id": v.id, "title": v.title, "level": v.level, "level_name": VUL_LEVEL.get(v.level, ""),
            "link": f"/vulns/{v.id}",
        }
        for v in rows
    ]
    return TodoItemOut(category="my_vulns", name="我提交的漏洞", count=count, items=items)


async def _retest_todos(
    session: AsyncSession, user: User, *, offset: int = 0, limit: int = _TODO_ITEM_LIMIT,
) -> TodoItemOut:
    cond = [TestingPlan.status.in_((PlanStatus.RETEST_APPLY, PlanStatus.RETESTING))]
    if not _has(user, "special:manage"):
        cond.append(
            exists().where(
                testing_plan_testers.c.testing_plan_id == TestingPlan.id,
                testing_plan_testers.c.user_id == user.id,
            )
        )
    count = (await session.execute(select(func.count(TestingPlan.id)).where(*cond))).scalar_one()
    rows = (
        await session.execute(
            select(TestingPlan)
            .where(*cond)
            .order_by(TestingPlan.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    items = [
        {
            "id": p.id, "ticket_id": p.ticket_id, "system_name": p.system_name,
            "link": _PLAN_LINK.format(id=p.id),
        }
        for p in rows
    ]
    return TodoItemOut(category="retest", name="待复测", count=count, items=items)


async def _import_todos(
    session: AsyncSession, user: User, *, offset: int = 0, limit: int = _TODO_ITEM_LIMIT,
) -> TodoItemOut:
    if not _has(user, "import:manage"):
        return TodoItemOut(category="import_pending", name="待确认导入", count=0)
    cond = [ImportBatch.status == "parsed"]
    count = (await session.execute(select(func.count(ImportBatch.id)).where(*cond))).scalar_one()
    rows = (
        await session.execute(
            select(ImportBatch)
            .where(*cond)
            .order_by(ImportBatch.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    items = [
        {
            "id": b.id, "filename": b.filename, "total": b.total,
            "link": f"/reports/imports/{b.id}",
        }
        for b in rows
    ]
    return TodoItemOut(category="import_pending", name="待确认导入", count=count, items=items)


async def _sla_todo(
    session: AsyncSession, user: User, state: str, *,
    offset: int = 0, limit: int = _TODO_ITEM_LIMIT,
) -> TodoItemOut:
    """SLA 临期 / 逾期待办（复用 sla_service 的同一判定条件）。"""
    config = await sla_service.runtime(session)
    name = "SLA 临期" if state == "due_soon" else "SLA 逾期"
    category = "sla_due" if state == "due_soon" else "sla_overdue"
    if not config.enabled:
        return TodoItemOut(category=category, name=name, count=0)
    cond = sla_service.sla_state_condition(state, config)
    if not (_has(user, "vuln:audit") or _has(user, "vuln:manage")):
        cond = [*cond, Vul.submitter_id == user.id]
    count = (await session.execute(select(func.count(Vul.id)).where(*cond))).scalar_one()
    rows = (
        await session.execute(
            select(Vul).where(*cond).order_by(Vul.due_at).offset(offset).limit(limit)
        )
    ).scalars().all()
    items = []
    for v in rows:
        info = sla_service.evaluate(v, config)
        items.append({
            "id": v.id, "title": v.title, "level": v.level,
            "level_name": VUL_LEVEL.get(v.level, ""),
            "due_at": v.due_at.isoformat() if v.due_at else "",
            "overdue_days": info["sla_overdue_days"],
            "link": f"/vulns/{v.id}",
        })
    return TodoItemOut(category=category, name=name, count=count, items=items)


async def _claimed_plan_todos(
    session: AsyncSession,
    user: User,
    *,
    category: str,
    name: str,
    statuses: tuple[PlanStatus, ...],
    offset: int = 0,
    limit: int = _TODO_ITEM_LIMIT,
) -> TodoItemOut:
    """当前用户已认领且状态命中的工单；认领关系是唯一可见性边界。"""
    cond = [
        TestingPlan.status.in_(statuses),
        exists().where(
            testing_plan_testers.c.testing_plan_id == TestingPlan.id,
            testing_plan_testers.c.user_id == user.id,
        ),
    ]
    count = (await session.execute(select(func.count(TestingPlan.id)).where(*cond))).scalar_one()
    rows = (
        await session.execute(
            select(TestingPlan)
            .where(*cond)
            .order_by(TestingPlan.id.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()
    items = [
        {
            "id": p.id,
            "ticket_id": p.ticket_id,
            "system_name": p.system_name,
            "department": p.department,
            "status": p.status,
            "status_name": TESTING_PLAN_STATUS.get(p.status, ""),
            "link": _PLAN_LINK.format(id=p.id),
        }
        for p in rows
    ]
    return TodoItemOut(category=category, name=name, count=count, items=items)


async def _todo_group(
    session: AsyncSession, user: User, category: str, *,
    offset: int = 0, limit: int = _TODO_ITEM_LIMIT,
) -> TodoItemOut:
    """按分类取待办明细（聚合接口与展开接口共用，保证口径一致）。"""
    if category == "plan_unclaimed":
        return await _unclaimed_todos(session, offset=offset, limit=limit)
    if category == "my_vulns":
        return await _my_vuln_todos(session, user, offset=offset, limit=limit)
    if category == "retest":
        return await _retest_todos(session, user, offset=offset, limit=limit)
    if category == "import_pending":
        return await _import_todos(session, user, offset=offset, limit=limit)
    if category in ("sla_due", "sla_overdue"):
        state = "due_soon" if category == "sla_due" else "overdue"
        return await _sla_todo(session, user, state, offset=offset, limit=limit)
    if category == "plan_in_progress":
        return await _claimed_plan_todos(
            session, user, category=category, name="进行中工单",
            statuses=(PlanStatus.TESTING,), offset=offset, limit=limit,
        )
    if category == "plan_completed":
        return await _claimed_plan_todos(
            session, user, category=category, name="已完成工单",
            statuses=(PlanStatus.RETEST_DONE, PlanStatus.PASSED),
            offset=offset, limit=limit,
        )
    raise HTTPException(404, "未知的待办分类")


@router.get("/todos", response_model=TodoSummaryOut)
async def list_todos(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """个人待办聚合：原有分类 + 当前用户已认领的进行中 / 已完成工单。"""
    categories = (
        "plan_unclaimed", "my_vulns", "retest", "import_pending", "sla_due", "sla_overdue",
        "plan_in_progress", "plan_completed",
    )
    groups = [await _todo_group(session, user, c) for c in categories]
    always_visible = ("my_vulns", "retest", "plan_in_progress", "plan_completed")
    groups = [g for g in groups if g.count > 0 or g.category in always_visible]
    return TodoSummaryOut(total=sum(g.count for g in groups), groups=groups)


@router.get("/todos/{category}", response_model=TodoItemPageOut)
async def list_todo_items(
    category: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """单个待办分类的完整明细：工作台「查看全部」在卡片内分页展开，不跳转到其他列表页。"""
    group = await _todo_group(session, user, category, offset=(page - 1) * size, limit=size)
    return TodoItemPageOut(
        category=group.category, name=group.name, total=group.count, items=group.items,
    )
