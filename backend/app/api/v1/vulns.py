from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_LAYER, VUL_LEVEL, VUL_STATUS, VUL_TRANSITIONS, VUL_TYPE
from app.core.deps import get_current_user, require_perm, user_permissions
from app.core.query import get_or_404, paginate
from app.db import get_session
from app.models import Asset, User, Vul, VulLog, VulRetestRecord
from app.schemas import (
    Page,
    VulBatchDeleteIn,
    VulBatchIn,
    VulDelayIn,
    VulFieldsIn,
    VulIn,
    VulLogOut,
    VulOut,
    VulRetestRecordIn,
    VulRetestRecordOut,
    VulTransitionIn,
    VulUpdateIn,
)
from app.services import plan_service, vuln_service

router = APIRouter(prefix="/vulns", tags=["漏洞"])


def build_vul_out(vul: Vul) -> VulOut:
    out = VulOut.model_validate(vul)
    out.asset_ids = [a.id for a in vul.assets]
    # 归属部门取自关联资产，去重后拼接
    out.department = "、".join(dict.fromkeys(a.department for a in vul.assets if a.department))
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

    stmt = select(Vul).where(*cond).order_by(Vul.submit_time.desc())
    total, vulns = await paginate(session, stmt, page, size)
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
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    return build_vul_out(vul)


@router.put("/{vul_id}", response_model=VulOut)
async def update_vuln(
    vul_id: int,
    body: VulUpdateIn,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    perms = user_permissions(user)
    if "*" not in perms and "vuln:manage" not in perms and vul.submitter_id != user.id:
        raise HTTPException(403, "只有提交人或漏洞管理员可以编辑")
    data = body.model_dump()
    asset_ids = data.pop("asset_ids", [])
    new_status = data.pop("status", None)
    old_plan_id = vul.testing_plan_id
    if data.get("testing_plan_id") != old_plan_id:
        await _check_plan_access(session, data.get("testing_plan_id"), user)
    for k, v in data.items():
        setattr(vul, k, v)
    vul.assets = await _fetch_assets(session, asset_ids)
    vuln_service.add_log(session, vul, user, "编辑漏洞")
    # 编辑页下拉直接调整状态：写日志并双向联动报告/测试计划状态
    if new_status is not None and new_status != vul.status:
        vuln_service.set_status(session, vul, new_status, user, "编辑页调整状态")
        await vuln_service.sync_report_completion(session, [vul.id])
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


@router.post("/batch-delete")
async def delete_vulns_batch(
    body: VulBatchDeleteIn,
    _: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """批量删除漏洞，删除后重算涉及测试计划的统计。"""
    vulns = (
        await session.execute(select(Vul).where(Vul.id.in_(body.ids)))
    ).scalars().all()
    plan_ids = {v.testing_plan_id for v in vulns}
    for v in vulns:
        await session.delete(v)
    await session.flush()
    for plan_id in plan_ids:
        await plan_service.refresh_stats(session, plan_id)
    await session.commit()
    return {"msg": "删除成功", "deleted": len(vulns)}


@router.get("/{vul_id}/transitions")
async def allowed_transitions(
    vul_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    return [
        {"status": s, "name": VUL_STATUS[s]}
        for s in sorted(VUL_TRANSITIONS.get(vul.status, set()))
    ]


@router.post("/{vul_id}/status", response_model=VulOut)
async def set_vuln_status(
    vul_id: int,
    body: VulTransitionIn,
    user: User = Depends(require_perm("vuln:audit")),
    session: AsyncSession = Depends(get_session),
):
    """直接设置漏洞状态（报告编辑页状态标签点选），不受状态机流转限制。"""
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    vuln_service.set_status(session, vul, body.status, user, body.comment or "报告编辑页调整状态")
    # 状态任意变化均双向联动报告/测试计划（闭环标记与回退）
    await vuln_service.sync_report_completion(session, [vul.id])
    await session.commit()
    await session.refresh(vul)
    return build_vul_out(vul)


@router.patch("/{vul_id}/fields", response_model=VulOut)
async def patch_vuln_fields(
    vul_id: int,
    body: VulFieldsIn,
    user: User = Depends(require_perm("vuln:audit")),
    session: AsyncSession = Depends(get_session),
):
    """报告编辑页下拉框快捷调整漏洞字段（状态/等级/类型/所在层），仅更新传入且有变化的字段。"""
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    dicts = {"level": VUL_LEVEL, "vul_type": VUL_TYPE, "layer": VUL_LAYER}
    changed_fields = []
    for field, label in (("level", "漏洞等级"), ("vul_type", "漏洞类型"), ("layer", "所在层")):
        value = getattr(body, field)
        if value is None or value == getattr(vul, field):
            continue
        if value not in dicts[field]:
            raise HTTPException(400, f"非法{label}: {value}")
        old = getattr(vul, field)
        setattr(vul, field, value)
        changed_fields.append(f"{label} {dicts[field][old]} → {dicts[field][value]}")
    if changed_fields:
        vuln_service.add_log(session, vul, user, "报告编辑页调整字段", "；".join(changed_fields))
    status_changed = body.status is not None and body.status != vul.status
    if status_changed:
        vuln_service.set_status(session, vul, body.status, user, "报告编辑页调整状态")
        await vuln_service.sync_report_completion(session, [vul.id])
    # 等级变化后重算关联计划的漏洞统计
    if any(f.startswith("漏洞等级") for f in changed_fields):
        await plan_service.refresh_stats(session, vul.testing_plan_id)
    await session.commit()
    await session.refresh(vul)
    return build_vul_out(vul)


@router.post("/{vul_id}/transition", response_model=VulOut)
async def transition_vuln(
    vul_id: int,
    body: VulTransitionIn,
    user: User = Depends(require_perm("vuln:audit")),
    session: AsyncSession = Depends(get_session),
):
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    # 复测编辑面板可随流转一并提交复测详情
    comment = body.comment
    if body.retest_html is not None:
        vul.retest_html = body.retest_html
        vul.retest_json = body.retest_json
        comment = comment or "复测详情已更新"
    await vuln_service.transition(session, vul, body.status, user, comment)
    # 状态流转后双向联动报告/测试计划（全部闭环自动标记完成，回退自动重开）
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
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
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


# ---------- 复测记录（复测处理页） ----------
async def _get_retest_record(session: AsyncSession, vul_id: int, record_id: int) -> VulRetestRecord:
    record = await session.get(VulRetestRecord, record_id)
    if record is None or record.vul_id != vul_id:
        raise HTTPException(404, "复测记录不存在")
    return record


async def _sync_vul_retest_html(session: AsyncSession, vul: Vul) -> None:
    """将该漏洞全部复测记录聚合写入 Vul.retest_html，保持详情页/报告读取口径一致。"""
    records = (
        await session.execute(
            select(VulRetestRecord).where(VulRetestRecord.vul_id == vul.id)
            .order_by(VulRetestRecord.create_time, VulRetestRecord.id)
        )
    ).scalars().all()
    parts = [r.content_html for r in records if r.content_html]
    if len(parts) > 1:
        parts = [f"<p><strong>复测记录 {i}：</strong></p>{h}" for i, h in enumerate(parts, 1)]
    vul.retest_html = "".join(parts)
    vul.retest_json = None


@router.get("/{vul_id}/retests", response_model=list[VulRetestRecordOut])
async def list_retest_records(
    vul_id: int,
    _: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if await session.get(Vul, vul_id) is None:
        raise HTTPException(404, "漏洞不存在")
    records = (
        await session.execute(
            select(VulRetestRecord).where(VulRetestRecord.vul_id == vul_id)
            .order_by(VulRetestRecord.create_time, VulRetestRecord.id)
        )
    ).scalars().all()
    return records


@router.post("/{vul_id}/retests", response_model=VulRetestRecordOut)
async def create_retest_record(
    vul_id: int,
    body: VulRetestRecordIn,
    user: User = Depends(require_perm("vuln:audit")),
    session: AsyncSession = Depends(get_session),
):
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    record = VulRetestRecord(
        vul_id=vul_id, content_html=body.content_html, content_json=body.content_json,
        creator_id=user.id, username=user.username,
    )
    session.add(record)
    vuln_service.add_log(session, vul, user, "新增复测记录")
    await session.flush()
    await _sync_vul_retest_html(session, vul)
    await session.commit()
    await session.refresh(record)
    return record


@router.put("/{vul_id}/retests/{record_id}", response_model=VulRetestRecordOut)
async def update_retest_record(
    vul_id: int,
    record_id: int,
    body: VulRetestRecordIn,
    user: User = Depends(require_perm("vuln:audit")),
    session: AsyncSession = Depends(get_session),
):
    record = await _get_retest_record(session, vul_id, record_id)
    record.content_html = body.content_html
    record.content_json = body.content_json
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    await session.flush()
    await _sync_vul_retest_html(session, vul)
    await session.commit()
    await session.refresh(record)
    return record


@router.delete("/{vul_id}/retests/{record_id}")
async def delete_retest_record(
    vul_id: int,
    record_id: int,
    user: User = Depends(require_perm("vuln:audit")),
    session: AsyncSession = Depends(get_session),
):
    record = await _get_retest_record(session, vul_id, record_id)
    vul = await session.get(Vul, vul_id)
    if vul is not None:
        vuln_service.add_log(session, vul, user, "删除复测记录", f"记录 #{record_id}")
    await session.delete(record)
    await session.flush()
    if vul is not None:
        await _sync_vul_retest_html(session, vul)
    await session.commit()
    return {"msg": "删除成功"}
