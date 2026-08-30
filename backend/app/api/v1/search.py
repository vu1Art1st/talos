"""⌘K 命令面板全局搜索：跨漏洞 / 资产 / 工单（渗透 + 漏扫基线）/ 报告的轻量聚合检索。"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, user_permissions
from app.db import get_session
from app.models import Asset, NonpenPlan, Report, TestingPlan, User, Vul

router = APIRouter(prefix="/search", tags=["Search"])

PER_PAGE = 5


@router.get("")
async def global_search(
    q: str = Query("", max_length=64),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """按关键字模糊匹配各实体的标题/名称字段，分组各返回最近 PER_PAGE 条。
    分区可见性跟随权限：资产/工单/报告仅对持相应管理权限（或通配符）的用户返回。"""
    kw = q.strip()
    if not kw:
        return {"vulns": [], "assets": [], "plans": [], "reports": []}
    like = f"%{kw}%"
    perms = user_permissions(user)
    wildcard = "*" in perms
    out: dict = {"vulns": [], "assets": [], "plans": [], "reports": []}

    rows = (await session.execute(
        select(Vul.id, Vul.title).where(Vul.title.ilike(like)).order_by(Vul.id.desc()).limit(PER_PAGE)
    )).all()
    out["vulns"] = [{"id": r[0], "title": r[1]} for r in rows]

    if wildcard or "asset:manage" in perms:
        rows = (await session.execute(
            select(Asset.id, Asset.name).where(Asset.name.ilike(like)).order_by(Asset.id.desc()).limit(PER_PAGE)
        )).all()
        out["assets"] = [{"id": r[0], "name": r[1]} for r in rows]

    if wildcard or "special:manage" in perms:
        plans: list[dict] = []
        rows = (await session.execute(
            select(TestingPlan.id, TestingPlan.plan_name, TestingPlan.system_name)
            .where(TestingPlan.plan_name.ilike(like) | TestingPlan.system_name.ilike(like))
            .order_by(TestingPlan.id.desc()).limit(PER_PAGE)
        )).all()
        plans.extend({"id": r[0], "title": r[1] or r[2], "type": "pen"} for r in rows)
        rows = (await session.execute(
            select(NonpenPlan.id, NonpenPlan.plan_name, NonpenPlan.system_name)
            .where(NonpenPlan.plan_name.ilike(like) | NonpenPlan.system_name.ilike(like))
            .order_by(NonpenPlan.id.desc()).limit(PER_PAGE)
        )).all()
        plans.extend({"id": r[0], "title": r[1] or r[2], "type": "nonpen"} for r in rows)
        out["plans"] = sorted(plans, key=lambda x: x["id"], reverse=True)[:PER_PAGE]

    if wildcard or "report:manage" in perms:
        rows = (await session.execute(
            select(Report.id, Report.title).where(Report.title.ilike(like)).order_by(Report.id.desc()).limit(PER_PAGE)
        )).all()
        out["reports"] = [{"id": r[0], "title": r[1]} for r in rows]

    return out
