"""专项管理 API：远程检测 / 测试计划 / 春耕行动，统一 special:manage 权限。"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm
from app.db import get_session
from app.models import RemoteTesting, Report, SpringAction, TestingPlan, User, Vul
from app.schemas import (
    Page,
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
    total = (await session.execute(select(func.count(RemoteTesting.id)).where(*cond))).scalar_one()
    items = (
        await session.execute(
            select(RemoteTesting).where(*cond).order_by(RemoteTesting.id.desc())
            .offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
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
    row = await session.get(RemoteTesting, row_id)
    if row is None:
        raise HTTPException(404, "远程检测记录不存在")
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
@router.get("/testing-plans", response_model=Page[TestingPlanOut])
async def list_testing_plans(
    search: str = "",
    status: int | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(
            TestingPlan.system_name.ilike(f"%{search}%")
            | TestingPlan.department.ilike(f"%{search}%")
            | TestingPlan.test_type.ilike(f"%{search}%")
        )
    if status is not None:
        cond.append(TestingPlan.status == status)
    total = (await session.execute(select(func.count(TestingPlan.id)).where(*cond))).scalar_one()
    items = (
        await session.execute(
            select(TestingPlan).where(*cond).order_by(TestingPlan.id.desc())
            .offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
    return Page(total=total, items=items)


@router.post("/testing-plans", response_model=TestingPlanOut)
async def create_testing_plan(
    body: TestingPlanIn,
    user: User = Depends(require_perm("special:manage")),
    session: AsyncSession = Depends(get_session),
):
    row = TestingPlan(**body.model_dump(), creator_id=user.id)
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
    row = await session.get(TestingPlan, row_id)
    if row is None:
        raise HTTPException(404, "测试计划不存在")
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
    row = await session.get(TestingPlan, row_id)
    if row is None:
        raise HTTPException(404, "测试计划不存在")
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
    row = await session.get(TestingPlan, row_id)
    if row is None:
        raise HTTPException(404, "测试计划不存在")
    if body.status != row.status and not plan_service.can_operate(user, row):
        raise HTTPException(403, "仅认领者或管理员可修改测试状态")
    for k, v in body.model_dump().items():
        setattr(row, k, v)
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
    total = (await session.execute(select(func.count(SpringAction.id)).where(*cond))).scalar_one()
    items = (
        await session.execute(
            select(SpringAction).where(*cond).order_by(SpringAction.id.desc())
            .offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
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
    row = await session.get(SpringAction, row_id)
    if row is None:
        raise HTTPException(404, "春耕行动记录不存在")
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
