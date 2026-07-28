from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_TRANSITIONS, VUL_STATUS
from app.core.deps import get_current_user, require_perm, user_permissions
from app.db import get_session
from app.models import Asset, User, Vul, VulLog
from app.schemas import (
    Page,
    VulBatchIn,
    VulDelayIn,
    VulIn,
    VulLogOut,
    VulOut,
    VulTransitionIn,
)
from app.services import plan_service, vuln_service

router = APIRouter(prefix="/vulns", tags=["漏洞"])


def build_vul_out(vul: Vul) -> VulOut:
    out = VulOut.model_validate(vul)
    out.asset_ids = [a.id for a in vul.assets]
    return out


async def _check_plan_access(session: AsyncSession, plan_id: int | None, user: User) -> None:
    """漏洞关联测试计划时：计划必须存在，且操作者为认领者或管理员。"""
    if plan_id is None:
        return
    plan = await plan_service.get_plan_or_400(session, plan_id)
    if not plan_service.can_operate(user, plan):
        raise HTTPException(403, "请先认领该测试计划后再录入漏洞")


async def _fetch_assets(session: AsyncSession, asset_ids: list[int]) -> list[Asset]:
    if not asset_ids:
        return []
    assets = (
        await session.execute(select(Asset).where(Asset.id.in_(asset_ids)))
    ).scalars().all()
    if len(assets) != len(set(asset_ids)):
        raise HTTPException(400, "存在无效的资产ID")
    return list(assets)


@router.get("", response_model=Page[VulOut])
async def list_vulns(
    search: str = "",
    status: int | None = None,
    level: int | None = None,
    vul_type: int | None = None,
    asset_id: int | None = None,
    testing_plan_id: int | None = None,
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
    if asset_id is not None:
        cond.append(Vul.assets.any(Asset.id == asset_id))
    if testing_plan_id is not None:
        cond.append(Vul.testing_plan_id == testing_plan_id)
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
    data = body.model_dump()
    asset_ids = data.pop("asset_ids", [])
    await _check_plan_access(session, data.get("testing_plan_id"), user)
    vul = Vul(**data, submitter_id=user.id)
    vul.assets = await _fetch_assets(session, asset_ids)
    session.add(vul)
    await session.flush()
    vuln_service.add_log(session, vul, user, "创建漏洞")
    await plan_service.refresh_stats(session, vul.testing_plan_id)
    await session.commit()
    await session.refresh(vul)
    return build_vul_out(vul)


@router.post("/batch", response_model=list[VulOut])
async def create_vulns_batch(
    body: VulBatchIn,
    user: User = Depends(require_perm("vuln:submit")),
    session: AsyncSession = Depends(get_session),
):
    """同一批资产下一次提交多个漏洞。漏洞项自带的 asset_ids 与批次级 asset_ids 合并。"""
    plan_ids = {item.testing_plan_id for item in body.vulns if item.testing_plan_id is not None}
    for plan_id in plan_ids:
        await _check_plan_access(session, plan_id, user)
    vulns: list[Vul] = []
    for item in body.vulns:
        data = item.model_dump()
        item_asset_ids = data.pop("asset_ids", [])
        merged_ids = list(dict.fromkeys([*body.asset_ids, *item_asset_ids]))
        vul = Vul(**data, submitter_id=user.id)
        vul.assets = await _fetch_assets(session, merged_ids)
        session.add(vul)
        await session.flush()
        vuln_service.add_log(session, vul, user, "创建漏洞", "批量提交")
        vulns.append(vul)
    for plan_id in plan_ids:
        await plan_service.refresh_stats(session, plan_id)
    await session.commit()
    for vul in vulns:
        await session.refresh(vul)
    return [build_vul_out(v) for v in vulns]


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
    data = body.model_dump()
    asset_ids = data.pop("asset_ids", [])
    old_plan_id = vul.testing_plan_id
    if data.get("testing_plan_id") != old_plan_id:
        await _check_plan_access(session, data.get("testing_plan_id"), user)
    for k, v in data.items():
        setattr(vul, k, v)
    vul.assets = await _fetch_assets(session, asset_ids)
    vuln_service.add_log(session, vul, user, "编辑漏洞")
    # 等级或关联计划变化后重算涉及计划的统计
    for plan_id in {old_plan_id, vul.testing_plan_id}:
        await plan_service.refresh_stats(session, plan_id)
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
        plan_id = vul.testing_plan_id
        await session.delete(vul)
        await session.flush()
        await plan_service.refresh_stats(session, plan_id)
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
    # 复测编辑面板可随流转一并提交复测详情
    comment = body.comment
    if body.retest_html is not None:
        vul.retest_html = body.retest_html
        vul.retest_json = body.retest_json
        comment = comment or "复测详情已更新"
    await vuln_service.transition(session, vul, body.status, user, comment)
    # 已修复/已忽略后检查关联报告是否全部处理完毕，自动标记报告已完成
    if body.status in (20, 60):
        await vuln_service.sync_report_completion(session, [vul.id])
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
