"""开放 API（F6）：个人访问令牌（PAT）认证的漏洞查询与远程推送接口。

- 认证：仅 PAT（Bearer tlp_xxx），见 core/deps.get_pat_user；JWT 会话令牌不接受；
- 限流：每令牌每分钟 PAT_RATE_LIMIT 次（认证依赖内统一执行）；
- 查询逻辑与站内列表/仪表盘共用（vulns._build_vuln_conditions / stats_service），口径一致；
- 远程漏洞推送只接收 Markdown，由 Talos 统一转换 HTML + ProseMirror JSON。
"""
import hashlib

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.vulns import _build_vuln_conditions, build_vul_out
from app.constants import PAT_VULN_WRITE_SCOPES
from app.core.deps import require_pat_admin_read, require_pat_perm, require_pat_read
from app.core.query import apply_sort, paginate_cursor, parse_int_list
from app.core.timeutil import parse_date
from app.db import get_session
from app.models import NotifyDelivery, User, Vul
from app.schemas import (
    NotifyDeliveryOut,
    Page,
    VulImageUploadOut,
    VulOut,
    VulPushIn,
    VulPushOut,
)
from app.services import idempotency, sla_service, vul_push_service
from app.services.audit_service import audit
from app.services.notify_service import notify
from app.services.stats_service import build_stats

router = APIRouter(prefix="/open", tags=["开放API"])
require_pat_vuln_write = require_pat_perm(
    "vuln:submit", scopes=PAT_VULN_WRITE_SCOPES,
)


async def _idem_begin(request: Request, session: AsyncSession, user: User, endpoint: str, payload):
    """写操作幂等前置：返回 `(需直接返回的响应 | None, 幂等键)`。"""
    key = idempotency.key_of(request.headers)
    if not key:
        return None, ""
    outcome, replay = await idempotency.claim(session, user.id, endpoint, key, payload)
    if outcome == "conflict":
        raise HTTPException(409, "Idempotency-Key 已用于不同的请求内容，请更换幂等键")
    if outcome == "replay" and replay:
        return JSONResponse(content=replay["response"], status_code=replay["status_code"]), key
    return None, key


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
    return Page(
        total=total,
        items=[await build_vul_out(session, v, user, can_edit=False) for v in vulns],
        **meta,
    )


@router.post("/testing-plans/{plan_id}/vulns", response_model=VulPushOut)
async def open_push_vulns(
    plan_id: int,
    body: VulPushIn,
    request: Request,
    user: User = Depends(require_pat_vuln_write),
    session: AsyncSession = Depends(get_session),
):
    """远程 Agent 批量推送漏洞到指定渗透测试工单。

    - 正文只接收 Markdown，由 Talos 生成 HTML + ProseMirror JSON；
    - 同一 `(source_system, external_id)` 长期幂等，内容变化返回 409；
    - 整批校验通过后原子提交，任一图片/类型/资产非法则整批失败。
    """
    endpoint = f"POST /open/testing-plans/{plan_id}/vulns"
    early, idem_key = await _idem_begin(
        request, session, user, endpoint, body.model_dump(mode="json"),
    )
    if early is not None:
        return early
    out = await vul_push_service.push_vulnerabilities(
        session, plan_id=plan_id, user=user, body=body,
    )
    await audit(session, request, "vuln_push", user, {
        "target": f"testing-plans/{plan_id}",
        "source_system": body.source_system,
        "created": out.summary.created,
        "duplicated": out.summary.duplicated,
        "external_ids": [item.external_id for item in body.items],
    })
    if out.summary.created:
        first_title = body.items[0].title if len(body.items) == 1 else "远程推送漏洞"
        await notify(
            request.app, session, "vuln_created",
            title=first_title, count=out.summary.created,
            operator=user.realname or user.username,
        )
    if idem_key:
        await idempotency.remember(session, user.id, endpoint, idem_key, 200, out)
    return out


@router.post("/testing-plans/{plan_id}/images", response_model=VulImageUploadOut)
async def open_upload_plan_image(
    plan_id: int,
    request: Request,
    file: UploadFile = File(...),
    source_system: str = Form(...),
    external_image_id: str | None = Form(None),
    user: User = Depends(require_pat_vuln_write),
    session: AsyncSession = Depends(get_session),
):
    """上传漏洞截图，返回可直接写入 Markdown 的图片片段。"""
    data = await file.read(vul_push_service.MAX_IMAGE_BYTES + 1)
    sha256 = hashlib.sha256(data).hexdigest()
    endpoint = f"POST /open/testing-plans/{plan_id}/images"
    early, idem_key = await _idem_begin(
        request, session, user, endpoint,
        {
            "source_system": source_system,
            "external_image_id": external_image_id,
            "sha256": sha256,
        },
    )
    if early is not None:
        return early
    out = await vul_push_service.upload_external_image(
        session,
        plan_id=plan_id,
        user=user,
        source_system=source_system,
        external_image_id=external_image_id,
        filename=file.filename or "",
        data=data,
    )
    await audit(session, request, "vuln_image_upload", user, {
        "target": f"testing-plans/{plan_id}",
        "source_system": source_system,
        "file_name": out.url.rsplit("/", 1)[-1],
        "sha256": out.sha256,
        "result": out.result,
    })
    if idem_key:
        await idempotency.remember(session, user.id, endpoint, idem_key, 200, out)
    return out


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
