"""开放 API（F6）：个人访问令牌（PAT）认证的只读接口，供内部看板与脚本集成。

- 认证：仅 PAT（Bearer tlp_xxx），见 core/deps.get_pat_user；JWT 会话令牌不接受；
- 限流：每令牌每分钟 PAT_RATE_LIMIT 次（认证依赖内统一执行）；
- 查询逻辑与站内列表/仪表盘共用（vulns._build_vuln_conditions / stats_service），口径一致。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.vulns import _build_vuln_conditions, build_vul_out
from app.core.deps import get_pat_user
from app.core.query import apply_sort, paginate, parse_int_list, parse_str_list
from app.core.timeutil import parse_date
from app.db import get_session
from app.models import User, Vul
from app.schemas import Page, VulOut
from app.services.stats_service import build_stats

router = APIRouter(prefix="/open", tags=["开放API"])


@router.get("/vulns", response_model=Page[VulOut])
async def open_list_vulns(
    search: str = "",
    status: int | None = None,
    level: int | None = None,
    levels: str = "",
    statuses: str = "",
    vul_type: int | None = None,
    vul_types: str = "",
    testing_plan_id: int | None = None,
    submit_time_from: str = "",
    submit_time_to: str = "",
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_pat_user),
    session: AsyncSession = Depends(get_session),
):
    """漏洞分页查询（筛选参数与站内 GET /vulns 一致，用户维度参数除外）。"""
    cond = _build_vuln_conditions(
        search=search, status=status, level=level, levels=parse_int_list(levels),
        statuses=parse_int_list(statuses),
        vul_type=vul_type, vul_types=parse_int_list(vul_types),
        testing_plan_id=testing_plan_id,
        submit_time_from=parse_date(submit_time_from),
        submit_time_to=parse_date(submit_time_to),
    )
    stmt = apply_sort(
        select(Vul).where(*cond),
        Vul, sort, order,
        {"id", "title", "level", "vul_type", "status", "submit_time"},
        Vul.submit_time.desc(),
    )
    total, vulns = await paginate(session, stmt, page, size)
    return Page(total=total, items=[build_vul_out(v) for v in vulns])


@router.get("/stats")
async def open_stats(
    date_from: str = "",
    date_to: str = "",
    department: str = "",
    source: int | None = None,
    level: int | None = None,
    user: User = Depends(get_pat_user),
    session: AsyncSession = Depends(get_session),
):
    """安全态势聚合（与站内 /dashboard/stats 共用 services/stats_service）。"""
    return await build_stats(
        session, date_from=date_from, date_to=date_to,
        department=department, source=source, level=level,
    )
