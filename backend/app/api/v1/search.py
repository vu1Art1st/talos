"""P2-4 全局搜索：跨漏洞 / 资产 / 工单（渗透 + 漏扫基线）/ 报告的权限感知检索。"""
import re
from html import unescape

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, case, cast, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db import get_session
from app.models import Asset, NonpenPlan, Report, ReportSection, TestingPlan, User, Vul

router = APIRouter(prefix="/search", tags=["Search"])

DEFAULT_LIMIT = 5
MAX_LIMIT = 10
_TYPES = {"vulns", "assets", "plans", "reports"}
_TAG_RE = re.compile(r"<[^>]+>")


def _plain_text(value: str, limit: int = 120) -> str:
    text = unescape(_TAG_RE.sub(" ", value or ""))
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _rank(col, kw: str):
    """标题类字段的固定排序：精确、前缀、包含、其它。"""
    lowered = func.lower(col)
    return case(
        (lowered == kw.lower(), literal(0)),
        (col.ilike(f"{kw}%"), literal(1)),
        (col.ilike(f"%{kw}%"), literal(2)),
        else_=literal(3),
    )


def _selected_types(raw: str) -> set[str]:
    requested = {part.strip() for part in (raw or "").split(",") if part.strip()}
    return requested & _TYPES if requested else set(_TYPES)


@router.get("")
async def global_search(
    q: str = Query("", max_length=64),
    types: str = Query("", max_length=64),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """按关键字检索业务实体；数据范围由 session 级 P2-1 scope 自动注入。"""
    kw = q.strip()
    out: dict[str, list[dict]] = {"vulns": [], "assets": [], "plans": [], "reports": []}
    if not kw:
        return out
    selected = _selected_types(types)
    like = f"%{kw}%"

    if "vulns" in selected:
        stmt = (
            select(Vul.id, Vul.title, Vul.affected_url)
            .where(or_(Vul.title.ilike(like), Vul.affected_url.ilike(like)))
            .order_by(_rank(Vul.title, kw), Vul.id.desc())
            .limit(limit)
        )
        out["vulns"] = [
            {
                "id": row.id,
                "title": row.title,
                "match": "affected_url" if kw.lower() in (row.affected_url or "").lower()
                else "title",
                "snippet": _plain_text(row.affected_url or row.title),
            }
            for row in (await session.execute(stmt)).all()
        ]

    if "assets" in selected:
        url_text = cast(Asset.public_urls, String)
        internal_text = cast(Asset.internal_urls, String)
        stmt = (
            select(Asset.id, Asset.name, Asset.sub_system, Asset.department)
            .where(
                or_(
                    Asset.name.ilike(like),
                    Asset.sub_system.ilike(like),
                    Asset.department.ilike(like),
                    url_text.ilike(like),
                    internal_text.ilike(like),
                )
            )
            .order_by(_rank(Asset.name, kw), Asset.id.desc())
            .limit(limit)
        )
        out["assets"] = [
            {
                "id": row.id,
                "name": row.name,
                "snippet": _plain_text(" / ".join(
                    part for part in (row.name, row.sub_system, row.department) if part
                )),
            }
            for row in (await session.execute(stmt)).all()
        ]

    if "plans" in selected:
        plan_stmt = (
            select(
                TestingPlan.id,
                TestingPlan.plan_name,
                TestingPlan.system_name,
                TestingPlan.department,
                literal("pen").label("plan_type"),
            )
            .where(or_(
                TestingPlan.plan_name.ilike(like),
                TestingPlan.system_name.ilike(like),
                TestingPlan.department.ilike(like),
            ))
            .order_by(_rank(TestingPlan.plan_name, kw), TestingPlan.id.desc())
            .limit(limit)
        )
        rows = (await session.execute(plan_stmt)).all()
        plans = [
            {
                "id": row.id,
                "title": row.plan_name or row.system_name,
                "type": "pen",
                "snippet": _plain_text(" / ".join(
                    part for part in (row.plan_name, row.system_name, row.department) if part
                )),
            }
            for row in rows
        ]
        if len(plans) < limit:
            nonpen_stmt = (
                select(
                    NonpenPlan.id,
                    NonpenPlan.plan_name,
                    NonpenPlan.system_name,
                    NonpenPlan.department,
                    literal("nonpen").label("plan_type"),
                )
                .where(or_(
                    NonpenPlan.plan_name.ilike(like),
                    NonpenPlan.system_name.ilike(like),
                    NonpenPlan.department.ilike(like),
                ))
                .order_by(_rank(NonpenPlan.plan_name, kw), NonpenPlan.id.desc())
                .limit(limit - len(plans))
            )
            rows = (await session.execute(nonpen_stmt)).all()
            plans.extend(
                {
                    "id": row.id,
                    "title": row.plan_name or row.system_name,
                    "type": "nonpen",
                    "snippet": _plain_text(" / ".join(
                        part for part in (row.plan_name, row.system_name, row.department) if part
                    )),
                }
                for row in rows
            )
        out["plans"] = plans

    if "reports" in selected:
        section_match = select(ReportSection.report_id).where(or_(
            ReportSection.title.ilike(like),
            ReportSection.content_html.ilike(like),
        ))
        stmt = (
            select(Report.id, Report.title, Report.project_name)
            .where(or_(
                Report.title.ilike(like),
                Report.project_name.ilike(like),
                Report.id.in_(section_match),
            ))
            .order_by(_rank(Report.title, kw), Report.id.desc())
            .limit(limit)
        )
        out["reports"] = [
            {
                "id": row.id,
                "title": row.title,
                "snippet": _plain_text(
                    f"{row.title} / {row.project_name}" if row.project_name else row.title
                ),
            }
            for row in (await session.execute(stmt)).all()
        ]

    return out
