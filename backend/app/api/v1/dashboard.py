"""安全态势（P1-7）：聚合统计 + 个人视图 / 部门默认视图。"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_perm, user_permissions
from app.core.query import delete_by_id_if_exists, get_or_404
from app.db import get_session
from app.models import DashboardView, User
from app.schemas import DashboardViewIn, DashboardViewOut
from app.services.audit_service import audit
from app.services.stats_service import build_stats

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def stats(
    date_from: str = "",
    date_to: str = "",
    department: str = "",
    source: int | None = None,
    level: int | None = None,
    _: User = Depends(require_perm("dashboard:view")),
    session: AsyncSession = Depends(get_session),
):
    """安全态势聚合（services/stats_service 与开放 API /open/stats 共用口径）。

    返回含 SLA（逾期率 / 平均修复时长）、运营指标（复测积压 / 报告未交付）与
    `cached_at`（统计生成时间，短 TTL 缓存），与列表、导出同源。
    """
    return await build_stats(
        session, date_from=date_from, date_to=date_to,
        department=department, source=source, level=level,
    )


# ---------- 看板视图（P1-7：个人视图 / 部门默认视图） ----------
@router.get("/views", response_model=list[DashboardViewOut])
async def list_views(
    user: User = Depends(require_perm("dashboard:view")),
    session: AsyncSession = Depends(get_session),
):
    """当前用户可见的视图：自己的个人视图 + 全部部门默认视图。"""
    rows = (
        await session.execute(
            select(DashboardView)
            .where(
                or_(
                    DashboardView.user_id == user.id,
                    DashboardView.scope == "department",
                )
            )
            .order_by(DashboardView.scope, DashboardView.id.desc())
        )
    ).scalars().all()
    return rows


@router.post("/views", response_model=DashboardViewOut)
async def save_view(
    body: DashboardViewIn,
    request: Request,
    user: User = Depends(require_perm("dashboard:view")),
    session: AsyncSession = Depends(get_session),
):
    """保存视图。`scope=department` 需要 `dashboard:view`（与站内看板同权限，首期不做跨租户隔离）。"""
    row = DashboardView(
        user_id=user.id, name=body.name, scope=body.scope, department=body.department,
        query=body.query.model_dump(), is_default=body.is_default,
    )
    session.add(row)
    await session.flush()
    if body.is_default:
        # 同一用户同一 scope 下只保留一个默认视图
        others = (
            await session.execute(
                select(DashboardView).where(
                    DashboardView.user_id == user.id,
                    DashboardView.scope == body.scope,
                    DashboardView.id != row.id,
                )
            )
        ).scalars().all()
        for item in others:
            item.is_default = False
    await session.commit()
    await session.refresh(row)
    await audit(session, request, "dashboard_view_save", user, {
        "name": row.name, "scope": row.scope, "department": row.department,
    })
    return row


@router.delete("/views/{view_id}")
async def delete_view(
    view_id: int,
    request: Request,
    user: User = Depends(require_perm("dashboard:view")),
    session: AsyncSession = Depends(get_session),
):
    """删除视图：个人视图仅本人可删；部门默认视图需 `system:manage`。"""
    row = await get_or_404(session, DashboardView, view_id, "看板视图不存在")
    if row.scope == "department":
        perms = user_permissions(user)
        if "*" not in perms and "system:manage" not in perms:
            raise HTTPException(403, "部门默认视图仅系统管理员可删除")
    elif row.user_id != user.id:
        raise HTTPException(404, "看板视图不存在")
    name = row.name
    await delete_by_id_if_exists(session, DashboardView, view_id)
    await session.commit()
    await audit(session, request, "dashboard_view_delete", user, {"name": name})
    return {"msg": "删除成功"}
