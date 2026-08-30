from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_LAYER, VUL_LEVEL, VUL_STATUS, VUL_TRANSITIONS, VUL_TYPE, VulStatus
from app.core.deps import get_current_user, require_perm, user_permissions
from app.core.query import get_or_404, paginate, apply_sort, parse_int_list, parse_str_list
from app.core.timeutil import parse_date
from app.db import get_session
from app.models import (
    Asset,
    ImportRecord,
    ReportSection,
    TestingPlan,
    User,
    Vul,
    VulLog,
    VulRetestRecord,
    spring_action_vulns,
    vuln_assets,
)
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
from app.services.audit_service import audit
from app.services.notify_service import notify

router = APIRouter(prefix="/vulns", tags=["漏洞"])


async def _notify_transition(
    request, session, user: User, vul: Vul,
    old_status: int | None, new_status: int | None, done_plans: list,
) -> None:
    """漏洞流转后的渠道通知：状态变化 → vuln_transition；计划闭环 → retest_completed。"""
    operator = user.realname or user.username
    if old_status is not None and new_status is not None and new_status != old_status:
        await notify(
            request.app, session, "vuln_transition", title=vul.title, operator=operator,
            **{
                "from": VUL_STATUS.get(old_status, str(old_status)),
                "to": VUL_STATUS.get(new_status, str(new_status)),
            },
        )
    for plan in done_plans:
        await notify(request.app, session, "retest_completed",
                     system=plan.system_name, operator=operator)


def build_vul_out(vul: Vul) -> VulOut:
    out = VulOut.model_validate(vul)
    out.asset_ids = [a.id for a in vul.assets]
    # 归属部门取自关联资产，去重后拼接
    out.department = "、".join(dict.fromkeys(a.department for a in vul.assets if a.department))
    return out


async def _check_plan_access(session: AsyncSession, plan_id: int | None, user: User) -> None:
    """漏洞关联测试计划时：计划必须存在，且操作者为该计划的认领者。

    录入漏洞阶段严格要求认领关系（管理员未认领也不放行），
    避免非认领账号把漏洞挂到其他测试计划下。"""
    if plan_id is None:
        return
    plan = await plan_service.get_plan_or_400(session, plan_id)
    if not plan_service.is_plan_claimant(user, plan):
        raise HTTPException(403, "仅已认领该渗透测试工单的账号可录入漏洞，请先认领该工单")


async def _check_vul_edit_access(session: AsyncSession, vul: Vul, user: User) -> None:
    """漏洞修改权限（录入漏洞阶段仅认领该计划的账号可修改）。

    - 已关联测试计划：仅认领该计划的账号（管理员未认领也不放行）可编辑；
    - 未关联计划：提交人或漏洞管理员（含 *）可编辑。"""
    if vul.testing_plan_id is not None:
        plan = await session.get(TestingPlan, vul.testing_plan_id)
        if plan is not None and not plan_service.is_plan_claimant(user, plan):
            raise HTTPException(403, "该漏洞已关联渗透测试工单，仅已认领该工单的账号可修改")
        return
    perms = user_permissions(user)
    if "*" not in perms and "vuln:manage" not in perms and vul.submitter_id != user.id:
        raise HTTPException(403, "只有提交人或漏洞管理员可以编辑")


async def _fetch_assets(session: AsyncSession, asset_ids: list[int]) -> list[Asset]:
    if not asset_ids:
        return []
    assets = (
        await session.execute(select(Asset).where(Asset.id.in_(asset_ids)))
    ).scalars().all()
    if len(assets) != len(set(asset_ids)):
        raise HTTPException(400, "存在无效的资产ID")
    return list(assets)


async def _clean_vul_references(session: AsyncSession, vul_ids: list[int]) -> None:
    """删除漏洞前解除外键引用，避免生产库（PostgreSQL 强制外键）删除失败返回 500。

    - report_sections.vul_id / import_records.vul_id：置空，保留报告章节与导入记录；
    - spring_action_vulns：删除春耕行动-漏洞关联行。"""
    if not vul_ids:
        return
    await session.execute(
        ReportSection.__table__.update()
        .where(ReportSection.vul_id.in_(vul_ids))
        .values(vul_id=None)
    )
    await session.execute(
        ImportRecord.__table__.update()
        .where(ImportRecord.vul_id.in_(vul_ids))
        .values(vul_id=None)
    )
    await session.execute(
        spring_action_vulns.delete().where(spring_action_vulns.c.vul_id.in_(vul_ids))
    )


def _build_vuln_conditions(
    *,
    search: str = "",
    status: int | None = None,
    level: int | None = None,
    levels: list[int] | None = None,
    statuses: list[int] | None = None,
    vul_type: int | None = None,
    vul_types: list[int] | None = None,
    asset_id: int | None = None,
    asset_ids: list[int] | None = None,
    department: str = "",
    departments: list[str] | None = None,
    system_type: str = "",
    system_types: list[str] | None = None,
    testing_plan_id: int | None = None,
    test_type: str = "",
    test_types: list[str] | None = None,
    submit_time_from: datetime | None = None,
    submit_time_to: datetime | None = None,
    mine: bool = False,
    user: User | None = None,
) -> list:
    """漏洞筛选条件构建器（列表查询与统计端点共用，保证统计口径与列表一致）。

    - level / levels：单选与多选互斥（levels 非空时优先用多选 IN 过滤），
      多选服务于统计表「按等级筛选」多选控件；
    - department / system_type：匹配漏洞「任一关联资产」的部门 / 系统类型，
      与 build_vul_out 归属部门展示口径一致；
    - test_type：匹配漏洞关联测试计划的测试类型；
    - 上述维度均提供多选（statuses / vul_types / asset_ids / departments /
      system_types / test_types）以支持前端筛选区的多选功能；
    - submit_time_from / submit_time_to：按漏洞录入时间做闭区间范围筛选。
    各单值参数保留以兼容旧调用，列表/多选参数非空时优先使用多选。
    """
    cond = []
    if search:
        # 关键词同时匹配漏洞标题 / 受影响 URL / 关联资产（系统）名称
        cond.append(
            Vul.title.ilike(f"%{search}%")
            | Vul.affected_url.ilike(f"%{search}%")
            | Vul.assets.any(Asset.name.ilike(f"%{search}%"))
        )
    if levels:
        cond.append(Vul.level.in_(levels))
    elif level is not None:
        cond.append(Vul.level == level)
    if statuses:
        cond.append(Vul.status.in_(statuses))
    elif status is not None:
        cond.append(Vul.status == status)
    if vul_types:
        cond.append(Vul.vul_type.in_(vul_types))
    elif vul_type is not None:
        cond.append(Vul.vul_type == vul_type)
    if asset_ids:
        cond.append(Vul.assets.any(Asset.id.in_(asset_ids)))
    elif asset_id is not None:
        cond.append(Vul.assets.any(Asset.id == asset_id))
    if departments:
        cond.append(Vul.assets.any(Asset.department.in_(departments)))
    elif department:
        cond.append(Vul.assets.any(Asset.department == department))
    if system_types:
        cond.append(Vul.assets.any(Asset.system_type.in_(system_types)))
    elif system_type:
        cond.append(Vul.assets.any(Asset.system_type == system_type))
    if testing_plan_id is not None:
        cond.append(Vul.testing_plan_id == testing_plan_id)
    if test_types:
        cond.append(
            Vul.testing_plan_id.in_(
                select(TestingPlan.id).where(TestingPlan.test_type.in_(test_types))
            )
        )
    elif test_type:
        cond.append(
            Vul.testing_plan_id.in_(
                select(TestingPlan.id).where(TestingPlan.test_type == test_type)
            )
        )
    if submit_time_from is not None:
        cond.append(Vul.submit_time >= submit_time_from)
    if submit_time_to is not None:
        # submit_time_to 取当天结束（含当天），等价于 < 次日 00:00
        cond.append(Vul.submit_time < submit_time_to + timedelta(days=1))
    if mine and user is not None:
        cond.append(Vul.submitter_id == user.id)
    return cond


@router.get("", response_model=Page[VulOut])
async def list_vulns(
    search: str = "",
    status: int | None = None,
    level: int | None = None,
    levels: str = "",
    statuses: str = "",
    vul_type: int | None = None,
    vul_types: str = "",
    asset_id: int | None = None,
    asset_ids: str = "",
    department: str = "",
    departments: str = "",
    system_type: str = "",
    system_types: str = "",
    testing_plan_id: int | None = None,
    test_type: str = "",
    test_types: str = "",
    submit_time_from: str = "",
    submit_time_to: str = "",
    mine: bool = False,
    sort: str = "",
    order: str = "desc",
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # 多选：逗号分隔字符串转列表；空字符串/全空 → None（等价不筛选）
    level_list = parse_int_list(levels)
    cond = _build_vuln_conditions(
        search=search, status=status, level=level, levels=level_list,
        statuses=parse_int_list(statuses),
        vul_type=vul_type, vul_types=parse_int_list(vul_types),
        asset_id=asset_id, asset_ids=parse_int_list(asset_ids),
        department=department, departments=parse_str_list(departments),
        system_type=system_type, system_types=parse_str_list(system_types),
        testing_plan_id=testing_plan_id, test_type=test_type,
        test_types=parse_str_list(test_types),
        submit_time_from=parse_date(submit_time_from),
        submit_time_to=parse_date(submit_time_to),
        mine=mine, user=user,
    )

    stmt = select(Vul).where(*cond)
    if sort == "level":
        # 需求7：同危害等级按录入时间升序（submit_time 升序，id 兜底），保证列表顺序稳定
        level_col = Vul.level.desc() if order == "desc" else Vul.level.asc()
        stmt = stmt.order_by(level_col, Vul.submit_time.asc(), Vul.id.asc())
    else:
        stmt = apply_sort(
            stmt, Vul, sort, order,
            {"id", "title", "level", "vul_type", "status", "submit_time"},
            Vul.submit_time.desc(),
        )
    total, vulns = await paginate(session, stmt, page, size)
    return Page(total=total, items=[build_vul_out(v) for v in vulns])


# 修复情况归并口径（与前端展示一致）：已修复 / 修复中(含复测中) / 未修复 / 其他(已忽略+暂不处理)
FIX_STATUS_DEF = [
    ("fixed", "已修复"),
    ("fixing", "修复中"),
    ("unfixed", "未修复"),
    ("other", "其他"),
]


@router.get("/stats")
async def vuln_stats(
    search: str = "",
    status: int | None = None,
    level: int | None = None,
    levels: str = "",
    statuses: str = "",
    vul_type: int | None = None,
    vul_types: str = "",
    asset_id: int | None = None,
    asset_ids: str = "",
    department: str = "",
    departments: str = "",
    system_type: str = "",
    system_types: str = "",
    testing_plan_id: int | None = None,
    test_type: str = "",
    test_types: str = "",
    submit_time_from: str = "",
    submit_time_to: str = "",
    mine: bool = False,
    user: User = Depends(require_perm("dashboard:view")),
    session: AsyncSession = Depends(get_session),
):
    """漏洞数量统计：支持按测试状态/资产系统类型/测试类型/具体资产/归属部门组合筛选，
    以及按录入时间范围筛选（submit_time_from / submit_time_to）。

    返回漏洞总数、等级分布、状态分布、修复情况归并，以及按部门/系统(资产)/系统类型/测试类型分组统计。
    分组统计基于漏洞-资产多对多关联（JOIN vuln_assets+Asset），同一漏洞关联多资产时
    会在分组维度重复计入（按关联关系统计），total 仍为漏洞条数。
    """
    level_list = parse_int_list(levels)
    cond = _build_vuln_conditions(
        search=search, status=status, level=level, levels=level_list,
        statuses=parse_int_list(statuses),
        vul_type=vul_type, vul_types=parse_int_list(vul_types),
        asset_id=asset_id, asset_ids=parse_int_list(asset_ids),
        department=department, departments=parse_str_list(departments),
        system_type=system_type, system_types=parse_str_list(system_types),
        testing_plan_id=testing_plan_id, test_type=test_type,
        test_types=parse_str_list(test_types),
        submit_time_from=parse_date(submit_time_from),
        submit_time_to=parse_date(submit_time_to),
        mine=mine, user=user,
    )

    total = (await session.execute(select(func.count(Vul.id)).where(*cond))).scalar_one()

    level_rows = (
        await session.execute(
            select(Vul.level, func.count(Vul.id)).where(*cond).group_by(Vul.level)
        )
    ).all()
    by_level = [
        {"level": lv, "name": VUL_LEVEL.get(lv, str(lv)), "count": c}
        for lv, c in sorted(level_rows)
    ]

    status_rows = (
        await session.execute(
            select(Vul.status, func.count(Vul.id)).where(*cond).group_by(Vul.status)
        )
    ).all()
    by_status = [
        {"status": s, "name": VUL_STATUS.get(s, str(s)), "count": c}
        for s, c in sorted(status_rows)
    ]

    # 修复情况归并（应用层聚合，避免多次分组查询）
    fix_agg: dict[str, int] = {}
    for s, c in status_rows:
        if s == VulStatus.FIXED:
            key = "fixed"
        elif s in (VulStatus.FIXING, VulStatus.RETESTING):
            key = "fixing"
        elif s == VulStatus.UNFIXED:
            key = "unfixed"
        else:
            key = "other"
        fix_agg[key] = fix_agg.get(key, 0) + c
    by_fix_status = [
        {"key": k, "name": n, "count": fix_agg.get(k, 0)} for k, n in FIX_STATUS_DEF
    ]

    # 按关联资产部门 / 系统类型分组统计（多对多 JOIN，无关联资产的漏洞不计入分组）
    dept_rows = (
        await session.execute(
            select(Asset.department, func.count(Vul.id))
            .select_from(Vul)
            .join(vuln_assets, vuln_assets.c.vul_id == Vul.id)
            .join(Asset, Asset.id == vuln_assets.c.asset_id)
            .where(*cond)
            .group_by(Asset.department)
        )
    ).all()
    by_department = [
        {"department": d or "未填写", "count": c}
        for d, c in sorted(dept_rows, key=lambda x: x[1], reverse=True)
    ]

    st_rows = (
        await session.execute(
            select(Asset.system_type, func.count(Vul.id))
            .select_from(Vul)
            .join(vuln_assets, vuln_assets.c.vul_id == Vul.id)
            .join(Asset, Asset.id == vuln_assets.c.asset_id)
            .where(*cond)
            .group_by(Asset.system_type)
        )
    ).all()
    by_system_type = [
        {"system_type": st or "未填写", "count": c}
        for st, c in sorted(st_rows, key=lambda x: x[1], reverse=True)
    ]

    # 按具体资产/系统分组统计（多对多 JOIN，与部门/系统类型同口径，无关联资产的漏洞不计入）
    asset_rows = (
        await session.execute(
            select(Asset.id, Asset.name, func.count(Vul.id))
            .select_from(Vul)
            .join(vuln_assets, vuln_assets.c.vul_id == Vul.id)
            .join(Asset, Asset.id == vuln_assets.c.asset_id)
            .where(*cond)
            .group_by(Asset.id, Asset.name)
        )
    ).all()
    by_asset = [
        {"asset_id": aid, "name": name or "未命名", "count": c}
        for aid, name, c in sorted(asset_rows, key=lambda x: x[2], reverse=True)
    ]

    # 资产归属部门去重列表（供「部门+系统组合统计」工具选择部门，覆盖所有资产部门）
    dept_names = (
        await session.execute(
            select(Asset.department).where(Asset.department.isnot(None)).distinct()
        )
    ).scalars().all()
    departments = sorted(d for d in dept_names if d.strip())

    # 按测试计划测试类型分组统计（LEFT JOIN，未关联计划的漏洞计入「未关联」）
    tt_rows = (
        await session.execute(
            select(TestingPlan.test_type, func.count(Vul.id))
            .select_from(Vul)
            .outerjoin(TestingPlan, TestingPlan.id == Vul.testing_plan_id)
            .where(*cond)
            .group_by(TestingPlan.test_type)
        )
    ).all()
    by_test_type = [
        {"test_type": t or "未关联", "count": c}
        for t, c in sorted(tt_rows, key=lambda x: x[1], reverse=True)
    ]

    # ---- 交叉表（pivot）：按 部门→系统 分行，列=等级×修复状态 ----
    # 查询原始粒度：每个 (部门, 资产ID, 资产名, 系统类型, 等级, 修复状态) 的漏洞数
    from sqlalchemy import case, literal_column

    _fix_case = case(
        (Vul.status == VulStatus.FIXED, "fixed"),
        (Vul.status.in_((VulStatus.FIXING, VulStatus.RETESTING)), "fixing"),
        (Vul.status == VulStatus.UNFIXED, "unfixed"),
        else_="other",
    ).label("fix_key")

    pivot_raw = (
        await session.execute(
            select(
                Asset.department,
                Asset.id.label("asset_id"),
                Asset.name.label("asset_name"),
                Asset.system_type,
                Vul.level,
                _fix_case,
                func.count(Vul.id).label("cnt"),
            )
            .select_from(Vul)
            .join(vuln_assets, vuln_assets.c.vul_id == Vul.id)
            .join(Asset, Asset.id == vuln_assets.c.asset_id)
            .where(*cond)
            .group_by(
                Asset.department, Asset.id, Asset.name,
                Asset.system_type, Vul.level,
                _fix_case,
            )
            .order_by(Asset.department, Asset.name, Vul.level)
        )
    ).all()

    # 聚合为前端可消费的透视表行
    _LEVELS = [10, 20, 30, 40]
    _row_map: dict[int, dict] = {}  # asset_id → row dict
    for d, aid, aname, stype, lv, fk, cnt in pivot_raw:
        if aid not in _row_map:
            _row_map[aid] = {
                "department": d or "未填写",
                "asset_id": aid,
                "asset_name": aname or "未命名",
                "system_type": stype or "未填写",
                "total": 0,
                "fixed_total": 0,
                "levels": {lv2: {"count": 0, "fixed": 0, "unfixed": 0} for lv2 in _LEVELS},
            }
        r = _row_map[aid]
        r["total"] += cnt
        if fk == "fixed":
            r["fixed_total"] += cnt
            r["levels"][lv]["fixed"] += cnt
        elif fk == "unfixed":
            r["levels"][lv]["unfixed"] += cnt
        r["levels"][lv]["count"] += cnt

    # 按 部门 → 资产名 排序
    pivot_rows = sorted(_row_map.values(), key=lambda x: (x["department"], x["asset_name"]))
    # 计算每行修复率
    for r in pivot_rows:
        r["fix_rate"] = round(r["fixed_total"] / r["total"] * 100) if r["total"] else 0

    # 合计行
    totals = {"total": 0, "fixed_total": 0, "levels": {lv: {"count": 0, "fixed": 0, "unfixed": 0} for lv in _LEVELS}}
    for r in pivot_rows:
        totals["total"] += r["total"]
        totals["fixed_total"] += r["fixed_total"]
        for lv in _LEVELS:
            for k in ("count", "fixed", "unfixed"):
                totals["levels"][lv][k] += r["levels"][lv][k]
    totals["fix_rate"] = round(totals["fixed_total"] / totals["total"] * 100) if totals["total"] else 0

    return {
        "total": total,
        "by_level": by_level,
        "by_status": by_status,
        "by_fix_status": by_fix_status,
        "by_department": by_department,
        "by_asset": by_asset,
        "departments": departments,
        "by_system_type": by_system_type,
        "by_test_type": by_test_type,
        "pivot": {
            "rows": pivot_rows,
            "totals": totals,
        },
    }


@router.post("", response_model=VulOut)
async def create_vuln(
    body: VulIn,
    request: Request,
    user: User = Depends(require_perm("vuln:submit")),
    session: AsyncSession = Depends(get_session),
):
    data = body.model_dump()
    asset_ids = data.pop("asset_ids", [])
    await _check_plan_access(session, data.get("testing_plan_id"), user)
    if data.get("testing_plan_id") is not None:
        # 关联渗透测试工单：漏洞来源固定为「渗透测试工单」（展示层派生），不落库来源值
        data["source"] = 0
    vul = Vul(**data, submitter_id=user.id)
    vul.assets = await _fetch_assets(session, asset_ids)
    session.add(vul)
    await session.flush()
    vuln_service.add_log(session, vul, user, "创建漏洞")
    # 无漏洞闭环重开：已确认「测试通过」的计划新增漏洞时自动回到「初测中」
    await plan_service.reopen_passed_plan(session, vul.testing_plan_id)
    await plan_service.refresh_stats(session, vul.testing_plan_id)
    await session.commit()
    await session.refresh(vul)
    await audit(session, request, "vuln_create", user, {"target": f"vulns/{vul.id}", "title": vul.title})
    await notify(request.app, session, "vuln_created",
                 title=vul.title, operator=user.realname or user.username)
    return build_vul_out(vul)


@router.post("/batch", response_model=list[VulOut])
async def create_vulns_batch(
    body: VulBatchIn,
    request: Request,
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
        if data.get("testing_plan_id") is not None:
            # 关联渗透测试工单：来源固定为「渗透测试工单」，不落库来源值
            data["source"] = 0
        merged_ids = list(dict.fromkeys([*body.asset_ids, *item_asset_ids]))
        vul = Vul(**data, submitter_id=user.id)
        vul.assets = await _fetch_assets(session, merged_ids)
        session.add(vul)
        await session.flush()
        vuln_service.add_log(session, vul, user, "创建漏洞", "批量提交")
        vulns.append(vul)
    for plan_id in plan_ids:
        await plan_service.reopen_passed_plan(session, plan_id)
        await plan_service.refresh_stats(session, plan_id)
    await session.commit()
    for vul in vulns:
        await session.refresh(vul)
    await audit(session, request, "vuln_create", user, {
        "op": "batch", "count": len(vulns),
        "titles": [v.title for v in vulns[:10]],
    })
    if vulns:
        await notify(request.app, session, "vuln_created",
                     title=vulns[0].title, count=len(vulns),
                     operator=user.realname or user.username)
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
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    await _check_vul_edit_access(session, vul, user)
    data = body.model_dump()
    asset_ids = data.pop("asset_ids", [])
    new_status = data.pop("status", None)
    old_status = vul.status
    old_plan_id = vul.testing_plan_id
    if data.get("testing_plan_id") != old_plan_id:
        await _check_plan_access(session, data.get("testing_plan_id"), user)
    for k, v in data.items():
        setattr(vul, k, v)
    # 关联渗透测试工单：来源恒为「渗透测试工单」，不可通过编辑修改来源值
    if vul.testing_plan_id is not None:
        vul.source = 0
    vul.assets = await _fetch_assets(session, asset_ids)
    vuln_service.add_log(session, vul, user, "编辑漏洞")
    done_plans: list = []
    # 编辑页下拉直接调整状态：写日志并双向联动报告/测试计划状态
    if new_status is not None and new_status != vul.status:
        await vuln_service.set_status(session, vul, new_status, user, "编辑页调整状态")
        done_plans = await vuln_service.sync_report_completion(session, [vul.id])
    # 等级或关联计划变化后重算涉及计划的统计；新关联计划若已确认无漏洞则自动重开
    await plan_service.reopen_passed_plan(session, vul.testing_plan_id)
    for plan_id in {old_plan_id, vul.testing_plan_id}:
        await plan_service.refresh_stats(session, plan_id)
    await session.commit()
    await session.refresh(vul)
    await _notify_transition(request, session, user, vul, old_status, new_status, done_plans)
    return build_vul_out(vul)


@router.delete("/{vul_id}")
async def delete_vuln(
    vul_id: int,
    request: Request,
    operator: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    vul = await session.get(Vul, vul_id)
    if vul:
        title = vul.title
        plan_id = vul.testing_plan_id
        await _clean_vul_references(session, [vul_id])
        await session.delete(vul)
        await session.flush()
        await plan_service.refresh_stats(session, plan_id)
        await session.commit()
        await audit(session, request, "vuln_delete", operator, {"target": f"vulns/{vul_id}", "title": title})
    return {"msg": "删除成功"}


@router.post("/batch-delete")
async def delete_vulns_batch(
    body: VulBatchDeleteIn,
    request: Request,
    operator: User = Depends(require_perm("vuln:manage")),
    session: AsyncSession = Depends(get_session),
):
    """批量删除漏洞，删除后重算涉及测试计划的统计。"""
    vulns = (
        await session.execute(select(Vul).where(Vul.id.in_(body.ids)))
    ).scalars().all()
    plan_ids = {v.testing_plan_id for v in vulns}
    await _clean_vul_references(session, body.ids)
    for v in vulns:
        await session.delete(v)
    await session.flush()
    for plan_id in plan_ids:
        await plan_service.refresh_stats(session, plan_id)
    await session.commit()
    await audit(session, request, "vuln_delete", operator, {
        "op": "batch", "count": len(vulns), "ids": body.ids[:50],
    })
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
    request: Request,
    user: User = Depends(require_perm("vuln:audit")),
    session: AsyncSession = Depends(get_session),
):
    """直接设置漏洞状态（报告编辑页状态标签点选），不受状态机流转限制。"""
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    old_status = vul.status
    await vuln_service.set_status(session, vul, body.status, user, body.comment or "报告编辑页调整状态")
    # 状态任意变化均双向联动报告/测试计划（闭环标记与回退）
    done_plans = await vuln_service.sync_report_completion(session, [vul.id])
    await session.commit()
    await session.refresh(vul)
    if body.status != old_status:
        await audit(session, request, "vuln_transition", user, {
            "target": f"vulns/{vul_id}", "title": vul.title,
            "from": VUL_STATUS.get(old_status, str(old_status)), "to": VUL_STATUS.get(body.status, str(body.status)),
        })
    await _notify_transition(request, session, user, vul, old_status, body.status, done_plans)
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
        await vuln_service.set_status(session, vul, body.status, user, "报告编辑页调整状态")
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
    request: Request,
    user: User = Depends(require_perm("vuln:audit")),
    session: AsyncSession = Depends(get_session),
):
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    old_status = vul.status
    # 复测编辑面板可随流转一并提交复测详情
    comment = body.comment
    if body.retest_html is not None:
        vul.retest_html = body.retest_html
        vul.retest_json = body.retest_json
        comment = comment or "复测详情已更新"
    await vuln_service.transition(
        session, vul, body.status, user, comment,
        retest_submitted=body.retest_html is not None,
    )
    # 状态流转后双向联动报告/测试计划（全部闭环自动标记完成，回退自动重开）
    done_plans = await vuln_service.sync_report_completion(session, [vul.id])
    await session.commit()
    await session.refresh(vul)
    if body.status != old_status:
        await audit(session, request, "vuln_transition", user, {
            "target": f"vulns/{vul_id}", "title": vul.title,
            "from": VUL_STATUS.get(old_status, str(old_status)), "to": VUL_STATUS.get(body.status, str(body.status)),
        })
    await _notify_transition(request, session, user, vul, old_status, body.status, done_plans)
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
    """将该漏洞全部复测记录聚合写入 Vul.retest_html，保持详情页/报告读取口径一致。

    标题优先取记录自定义 title；为空时按创建日期自动生成「复测记录yymmdd」：
    同日新增的第一条不带后缀，同一天内新增的多条依次追加 -1、-2 后缀
    （如复测记录250813、复测记录250813-1）。
    """
    records = (
        await session.execute(
            select(VulRetestRecord).where(VulRetestRecord.vul_id == vul.id)
            .order_by(VulRetestRecord.create_time, VulRetestRecord.id)
        )
    ).scalars().all()
    parts: list[str] = []
    day_counts: dict[str, int] = {}
    for r in records:
        if not r.content_html:
            continue
        if (r.title or "").strip():
            title = r.title.strip()
        else:
            date_key = r.create_time.strftime("%y%m%d") if r.create_time else ""
            n = day_counts.get(date_key, 0)
            day_counts[date_key] = n + 1
            title = f"复测记录{date_key}" if n == 0 else f"复测记录{date_key}-{n}"
        parts.append(f"<p><strong>{title}：</strong></p>{r.content_html}")
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
    request: Request,
    user: User = Depends(require_perm("vuln:audit")),
    session: AsyncSession = Depends(get_session),
):
    vul = await get_or_404(session, Vul, vul_id, "漏洞不存在")
    record = VulRetestRecord(
        vul_id=vul_id, title=body.title,
        content_html=body.content_html, content_json=body.content_json,
        creator_id=user.id, username=user.username,
    )
    session.add(record)
    vuln_service.add_log(session, vul, user, "新增复测记录")
    await session.flush()
    await _sync_vul_retest_html(session, vul)
    old_status = vul.status
    done_plans: list = []
    # 创建复测记录时可一并调整漏洞状态（复测未修复回修复中 / 已修复）：
    # 先聚合复测内容再流转，确保复测结论校验（必须填写复测详情）能够通过。
    if body.status is not None and body.status != vul.status:
        await vuln_service.transition(session, vul, body.status, user, "新增复测记录调整状态")
        done_plans = await vuln_service.sync_report_completion(session, [vul.id])
    await session.commit()
    await session.refresh(record)
    await _notify_transition(request, session, user, vul, old_status, body.status, done_plans)
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
    record.title = body.title
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
