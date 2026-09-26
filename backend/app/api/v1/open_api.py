"""开放 API（F6）：个人访问令牌（PAT）认证的只读接口，供内部看板与脚本集成。

- 认证：仅 PAT（Bearer tlp_xxx），见 core/deps.get_pat_user；JWT 会话令牌不接受；
- 限流：每令牌每分钟 PAT_RATE_LIMIT 次（认证依赖内统一执行）；
- 查询逻辑与站内列表/仪表盘共用（vulns._build_vuln_conditions / stats_service），口径一致。
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.vulns import _build_vuln_conditions, build_vul_out
from app.core.deps import require_pat_admin_read, require_pat_read
from app.core.query import apply_sort, paginate_cursor, parse_int_list
from app.core.timeutil import parse_date
from app.db import get_session
from app.models import NotifyDelivery, User, Vul
from app.schemas import NotifyDeliveryOut, Page, VulOut
from app.services import sla_service
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
    sla_state: str = "",
    sort: str = "",
    order: str = "desc",
    cursor: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(require_pat_read),
    session: AsyncSession = Depends(get_session),
):
    """漏洞分页查询（筛选参数与站内 GET /vulns 一致，用户维度参数除外）。

    分页（P1-6）：默认 `page`/`size` 偏移分页；传 `cursor`（上一页 `next_cursor`）
    则按 id 降序稳定遍历，响应返回 `has_more` / `next_cursor`。
    """
    cond = _build_vuln_conditions(
        search=search, status=status, level=level, levels=parse_int_list(levels),
        statuses=parse_int_list(statuses),
        vul_type=vul_type, vul_types=parse_int_list(vul_types),
        testing_plan_id=testing_plan_id,
        submit_time_from=parse_date(submit_time_from),
        submit_time_to=parse_date(submit_time_to),
    )
    if sla_state:
        cond.extend(sla_service.sla_state_condition(sla_state, await sla_service.runtime(session)))
    stmt = apply_sort(
        select(Vul).where(*cond),
        Vul, sort, order,
        {"id", "title", "level", "vul_type", "status", "submit_time"},
        Vul.submit_time.desc(),
    )
    total, vulns, meta = await paginate_cursor(
        session, stmt, page=page, size=size, cursor=cursor, id_col=Vul.id,
    )
    return Page(total=total, items=[await build_vul_out(session, v) for v in vulns], **meta)


@router.get("/stats")
async def open_stats(
    date_from: str = "",
    date_to: str = "",
    department: str = "",
    source: int | None = None,
    level: int | None = None,
    user: User = Depends(require_pat_read),
    session: AsyncSession = Depends(get_session),
):
    """安全态势聚合（与站内 /dashboard/stats 共用 services/stats_service，含 SLA 与运营指标）。"""
    return await build_stats(
        session, date_from=date_from, date_to=date_to,
        department=department, source=source, level=level,
    )


@router.get("/sla-config")
async def open_sla_config(
    user: User = Depends(require_pat_admin_read()),
    session: AsyncSession = Depends(get_session),
):
    """SLA 配置只读（P1-6「管理只读」scope 的落地端点）：策略、口径与开关。"""
    config = await sla_service.get_config(session)
    policies = await sla_service.load_policies(session)
    return {
        "config": {
            "enabled": config.enabled, "day_basis": config.day_basis,
            "default_days": config.default_days, "warn_hours": config.warn_hours,
            "allow_extend": config.allow_extend, "workdays": config.workdays,
            "holidays": config.holidays, "stop_statuses": config.stop_statuses,
        },
        "policies": [
            {"level": p.level, "days": p.days, "enabled": p.enabled}
            for p in sorted(policies.values(), key=lambda x: x.level)
        ],
    }


@router.get("/notify-deliveries", response_model=Page[NotifyDeliveryOut])
async def open_list_deliveries(
    status: str = "",
    event: str = "",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(require_pat_admin_read()),
    session: AsyncSession = Depends(get_session),
):
    """通知投递记录只读（P1-6「管理只读」）：便于外部监控接入投递成功率。"""
    cond = []
    if status:
        cond.append(NotifyDelivery.status == status)
    if event:
        cond.append(NotifyDelivery.event == event)
    total, items, meta = await paginate_cursor(
        session,
        select(NotifyDelivery).where(*cond).order_by(NotifyDelivery.id.desc()),
        page=page, size=size, id_col=NotifyDelivery.id,
    )
    return Page(total=total, items=[NotifyDeliveryOut.model_validate(i) for i in items], **meta)
