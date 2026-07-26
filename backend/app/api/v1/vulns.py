from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_TRANSITIONS, VUL_STATUS
from app.core.deps import get_current_user, require_perm, user_permissions
from app.db import get_session
from app.models import User, Vul, VulLog
from app.schemas import (
    Page,
    VulDelayIn,
    VulIn,
    VulLogOut,
    VulOut,
    VulTransitionIn,
)
from app.services import vuln_service

router = APIRouter(prefix="/vulns", tags=["漏洞"])


def build_vul_out(vul: Vul) -> VulOut:
    out = VulOut.model_validate(vul)
    out.app_name = vul.app.name if vul.app else ""
    return out


@router.get("", response_model=Page[VulOut])
async def list_vulns(
    search: str = "",
    status: int | None = None,
    level: int | None = None,
    vul_type: int | None = None,
    app_id: int | None = None,
    mine: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    cond = []
    if search:
        cond.append(Vul.title.ilike(f"%{search}%") | Vul.affected_url.ilike(f"%{search}%"))
    if status is not None:
        cond.append(Vul.status == status)
    if level is not None:
        cond.append(Vul.level == level)
    if vul_type is not None:
        cond.append(Vul.vul_type == vul_type)
    if app_id is not None:
        cond.append(Vul.app_id == app_id)
    if mine:
        cond.append(Vul.submitter_id == user.id)

    total = (await session.execute(select(func.count(Vul.id)).where(*cond))).scalar_one()
    vulns = (
        await session.execute(
            select(Vul).where(*cond).order_by(Vul.submit_time.desc())
            .offset((page - 1) * size).limit(size)
        )
    ).scalars().all()
    return Page(total=total, items=[build_vul_out(v) for v in vulns])


@router.post("", response_model=VulOut)
async def create_vuln(
    body: VulIn,
    user: User = Depends(require_perm("vuln:submit")),
    session: AsyncSession = Depends(get_session),
):
    vul = Vul(**body.model_dump(), submitter_id=user.id)
    session.add(vul)
    await session.flush()
    vuln_service.add_log(session, vul, user, "创建漏洞")
    await session.commit()
    await session.refresh(vul)
    return build_vul_out(vul)


@router.get("/{vul_id}", response_model=VulOut)
async def get_vuln(
    vul_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    vul = await session.get(Vul, vul_id)
    if vul is None:
        raise HTTPException(404, "漏洞不存在")
    return build_vul_out(vul)


@router.put("/{vul_id}", response_model=VulOut)
async def update_vuln(
    vul_id: int,
    body: VulIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    vul = await session.get(Vul, vul_id)
    if vul is None:
        raise HTTPException(404, "漏洞不存在")
    perms = user_permissions(user)
    if "*" not in perms and "vuln:manage" not in perms and vul.submitter_id != user.id:
        raise HTTPException(403, "只有提交人或漏洞管理员可以编辑")
    for k, v in body.model_dump().items():
        setattr(vul, k, v)
    vuln_service.add_log(session, vul, user, "编辑漏洞")
    await session.commit()
    await session.refresh(vul)
    return build_vul_out(vul)


@router.delete("/{vul_id}")
async def delete_vuln(
    vul_id: int,
    _: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    vul = await session.get(Vul, vul_id)
    if vul:
        await session.delete(vul)
        await session.commit()
    return {"msg": "删除成功"}


@router.get("/{vul_id}/transitions")
async def allowed_transitions(
    vul_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    vul = await session.get(Vul, vul_id)
    if vul is None:
        raise HTTPException(404, "漏洞不存在")
    return [
        {"status": s, "name": VUL_STATUS[s]}
        for s in sorted(VUL_TRANSITIONS.get(vul.status, set()))
    ]


@router.post("/{vul_id}/transition", response_model=VulOut)
async def transition_vuln(
    vul_id: int,
    body: VulTransitionIn,
    user: User = Depends(require_perm("vuln:audit")),
    session: AsyncSession = Depends(get_session),
):
    vul = await session.get(Vul, vul_id)
    if vul is None:
        raise HTTPException(404, "漏洞不存在")
    await vuln_service.transition(session, vul, body.status, user, body.comment)
    await session.commit()
    await session.refresh(vul)
    return build_vul_out(vul)


@router.post("/{vul_id}/delay", response_model=VulOut)
async def delay_vuln(
    vul_id: int,
    body: VulDelayIn,
    user: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    vul = await session.get(Vul, vul_id)
    if vul is None:
        raise HTTPException(404, "漏洞不存在")
    vul.delay_days = body.delay_days
    vul.delay_reason = body.delay_reason
    vuln_service.add_log(session, vul, user, "延期处理", f"延期{body.delay_days}天：{body.delay_reason}")
    await session.commit()
    await session.refresh(vul)
    return build_vul_out(vul)


@router.get("/{vul_id}/logs", response_model=list[VulLogOut])
async def vuln_logs(
    vul_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    logs = (
        await session.execute(
            select(VulLog).where(VulLog.vul_id == vul_id).order_by(VulLog.create_time.desc())
        )
    ).scalars().all()
    return logs
