"""SLA 修复时限（P1-1）：系统管理 > SLA 配置、等级策略、历史重算、统计与延期。"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_LEVEL, VUL_STATUS
from app.core.deps import get_current_user, require_perm
from app.core.query import delete_by_id_if_exists, get_or_404
from app.core.timeutil import now as tznow
from app.db import get_session
from app.models import SlaExtension, SlaPolicy, User, Vul
from app.schemas import (
    SlaConfigIn,
    SlaConfigOut,
    SlaExtendIn,
    SlaExtensionOut,
    SlaPolicyIn,
    SlaPolicyOut,
    SlaRecalculateIn,
    SlaRecalculateOut,
)
from app.services import sla_service, stats_cache, vul_service
from app.services.audit_service import audit

router = APIRouter(prefix="/sla", tags=["SLA"])


# ---------- 配置 ----------
@router.get("/config", response_model=SlaConfigOut)
async def get_sla_config(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """读取 SLA 全局配置（登录用户可读：列表与详情页需据此展示剩余时间）。"""
    return await sla_service.get_config(session)


@router.put("/config", response_model=SlaConfigOut)
async def update_sla_config(
    body: SlaConfigIn,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    """保存 SLA 策略配置。**只影响未来新漏洞**；历史数据需显式调用 /sla/recalculate。"""
    row = await sla_service.get_config(session)
    for key, value in body.model_dump().items():
        setattr(row, key, value)
    row.updated_by = operator.id
    await session.commit()
    await session.refresh(row)
    # 配置变更立即生效：失效运行时快照与统计缓存
    sla_service.invalidate_runtime()
    stats_cache.invalidate()
    await audit(session, request, "sla_config_update", operator, {
        "enabled": row.enabled, "day_basis": row.day_basis, "default_days": row.default_days,
    })
    return row


# ---------- 等级策略 ----------
@router.get("/policies", response_model=list[SlaPolicyOut])
async def list_sla_policies(
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return (await session.execute(select(SlaPolicy).order_by(SlaPolicy.level))).scalars().all()


@router.post("/policies", response_model=SlaPolicyOut)
async def upsert_sla_policy(
    body: SlaPolicyIn,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    """按等级新增或更新时限策略（同等级唯一）。"""
    row = (
        await session.execute(select(SlaPolicy).where(SlaPolicy.level == body.level))
    ).scalar_one_or_none()
    created = row is None
    if row is None:
        row = SlaPolicy(level=body.level)
        session.add(row)
    row.days = body.days
    row.enabled = body.enabled
    row.remark = body.remark
    await session.commit()
    await session.refresh(row)
    sla_service.invalidate_runtime()
    stats_cache.invalidate()
    await audit(session, request, "sla_policy_update", operator, {
        "op": "create" if created else "update",
        "level": body.level, "days": body.days, "enabled": body.enabled,
    })
    return row


@router.delete("/policies/{policy_id}")
async def delete_sla_policy(
    policy_id: int,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    """删除等级策略：该等级回落到配置的默认时限。"""
    row = await get_or_404(session, SlaPolicy, policy_id, "SLA 策略不存在")
    level = row.level
    await delete_by_id_if_exists(session, SlaPolicy, policy_id)
    await session.commit()
    sla_service.invalidate_runtime()
    stats_cache.invalidate()
    await audit(session, request, "sla_policy_update", operator, {"op": "delete", "level": level})
    return {"msg": "删除成功"}


# ---------- 历史重算 ----------
@router.post("/recalculate", response_model=SlaRecalculateOut)
async def recalculate_sla(
    body: SlaRecalculateIn,
    request: Request,
    operator: User = Depends(require_perm("system:manage")),
    session: AsyncSession = Depends(get_session),
):
    """按当前策略重算历史漏洞的截止时间（显式执行并留审计记录）。"""
    refreshed = await sla_service.refresh_vulns(session, scope=body.scope)
    await session.commit()
    stats_cache.invalidate()
    await audit(session, request, "sla_recalculate", operator, {
        "scope": body.scope, "refreshed": refreshed,
    })
    return SlaRecalculateOut(
        refreshed=refreshed, scope=body.scope,
        msg=f"已按当前策略重算 {refreshed} 条漏洞的修复截止时间",
    )


# ---------- 统计 ----------
@router.get("/stats")
async def sla_stats(
    date_from: str = "",
    date_to: str = "",
    department: str = "",
    source: int | None = None,
    level: int | None = None,
    _: User = Depends(require_perm("dashboard:view")),
    session: AsyncSession = Depends(get_session),
):
    return await sla_service.sla_stats(
        session, date_from=date_from, date_to=date_to,
        department=department, source=source, level=level,
    )


# ---------- 延期 ----------
def _parse_due_at(raw: str) -> datetime:
    text = (raw or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise HTTPException(400, "新到期时间格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM")


@router.get("/vulns/{vul_id}/extensions", response_model=list[SlaExtensionOut])
async def list_extensions(
    vul_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await get_or_404(session, Vul, vul_id, "漏洞不存在")
    return (
        await session.execute(
            select(SlaExtension)
            .where(SlaExtension.vul_id == vul_id)
            .order_by(SlaExtension.id.desc())
        )
    ).scalars().all()


@router.post("/vulns/{vul_id}/extend", response_model=SlaExtensionOut)
async def extend_sla(
    vul_id: int,
    body: SlaExtendIn,
    request: Request,
    operator: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """SLA 延期：记录原/新到期时间、原因与操作人，不允许无痕改期。"""
    config = await sla_service.get_config(session)
    if not config.allow_extend:
        raise HTTPException(400, "当前 SLA 配置不允许延期")
    if (body.new_due_at is None) == (body.extend_days is None):
        raise HTTPException(400, "请且仅请提供「新到期时间」或「顺延天数」之一")

    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    if vul.status in sla_service.stop_statuses(config):
        raise HTTPException(400, "漏洞已闭环（已修复/已忽略），无需延期")
    old_due = vul.due_at
    if body.new_due_at is not None:
        new_due = _parse_due_at(body.new_due_at)
    else:
        base = old_due or vul.submit_time or tznow()
        new_due = sla_service.add_days(base, int(body.extend_days or 0), config)
    if old_due is not None and new_due <= old_due:
        raise HTTPException(400, "新到期时间必须晚于原到期时间")

    vul.due_at = new_due
    row = SlaExtension(
        vul_id=vul.id, old_due_at=old_due, new_due_at=new_due,
        reason=body.reason, operator_id=operator.id, username=operator.username,
    )
    session.add(row)
    vul_service.add_log(
        session, vul, operator, "SLA 延期",
        f"{old_due.strftime('%Y-%m-%d %H:%M') if old_due else '未设置'} → "
        f"{new_due.strftime('%Y-%m-%d %H:%M')}：{body.reason}",
    )
    await session.commit()
    await session.refresh(row)
    stats_cache.invalidate()
    await audit(session, request, "sla_extend", operator, {
        "target": f"vulns/{vul_id}", "title": vul.title,
        "old_due_at": old_due.isoformat() if old_due else "", "new_due_at": new_due.isoformat(),
    })
    return row


# ---------- 元数据 ----------
@router.get("/meta")
async def sla_meta(_: User = Depends(get_current_user)):
    """SLA 相关字典（等级时限展示、状态口径），供前端下拉与图例使用。"""
    return {
        "levels": [{"level": k, "name": v} for k, v in VUL_LEVEL.items()],
        "statuses": [{"status": k, "name": v} for k, v in VUL_STATUS.items()],
    }
