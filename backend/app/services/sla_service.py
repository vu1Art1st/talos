"""SLA 修复时限（P1-1）：策略计算、截止时间落库、状态判定与统计。

**单源原则**：截止时间在漏洞新增 / 等级变更时由 `apply_to_vul` 计算并写入 `Vul.due_at`；
列表、详情、看板、导出与开放 API 一律以 `evaluate` / `sla_state_condition` 判定，
禁止在前端或路由里另行推演。统计口径见 `sla_stats`。

时间口径（验收要求）：一律按系统时区（默认 UTC+8）的**业务日**计算；
- 自然日：`start + N 天`（同一时刻）；
- 工作日：逐日推进，跳过 `workdays` 之外的星期与 `holidays` 中的日期，
  支持周末、跨月与闰日（日期运算基于 `datetime`，不手写月份天数）。

版本策略：策略变更默认只影响**未来新漏洞**；历史批量重算必须显式调用
`POST /sla/recalculate`（由路由写审计）。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import VUL_LEVEL, VUL_SOURCE
from app.core.timeutil import now as tznow
from app.models import SlaConfig, SlaPolicy, TestingPlan, Vul

logger = logging.getLogger(__name__)

# 单次推进的硬上限（防止 holidays 覆盖过多导致死循环）
_MAX_STEPS = 4000


@dataclass(frozen=True)
class SlaRuntime:
    """配置的只读快照（读路径用）：避免每行漏洞判定都去查 `sla_config`。

    与 `SlaConfig` 同名属性，`evaluate` / `stop_statuses` 等函数对两者通用（鸭子类型）。
    """

    enabled: bool
    day_basis: str
    default_days: int
    warn_hours: int
    allow_extend: bool
    workdays: tuple
    holidays: tuple
    stop_statuses: tuple


def to_runtime(config: SlaConfig) -> SlaRuntime:
    return SlaRuntime(
        enabled=bool(config.enabled),
        day_basis=config.day_basis or "natural",
        default_days=int(config.default_days or 7),
        warn_hours=int(config.warn_hours if config.warn_hours is not None else DEFAULT_WARN_HOURS),
        allow_extend=bool(config.allow_extend),
        workdays=tuple(config.workdays or []),
        holidays=tuple(str(h) for h in (config.holidays or [])),
        stop_statuses=tuple(int(s) for s in (config.stop_statuses or [20, 60])),
    )


# 运行时配置缓存：读路径（列表 / 详情 / 看板）每行都判定 SLA，逐行查库不可接受。
# TTL 很短，且写路径（保存配置）会显式失效，不会出现长时间陈旧。
_RUNTIME_TTL_SECONDS = 10
_runtime_cache: tuple[float, SlaRuntime] | None = None


async def runtime(session: AsyncSession, *, force: bool = False) -> SlaRuntime:
    """读取（带短 TTL 缓存）配置快照。"""
    global _runtime_cache
    if not force and _runtime_cache is not None:
        ts, cached = _runtime_cache
        if time.time() - ts <= _RUNTIME_TTL_SECONDS:
            return cached
    config = await get_config(session)
    snap = to_runtime(config)
    _runtime_cache = (time.time(), snap)
    return snap


def invalidate_runtime() -> None:
    """配置变更后失效快照（保存 SLA 配置时调用）。"""
    global _runtime_cache
    _runtime_cache = None

# 「即将到期」默认提前量（小时）；配置项 warn_hours 可覆盖
DEFAULT_WARN_HOURS = 24

# 默认等级时限（天）：仅用于初始化，之后由界面维护
DEFAULT_LEVEL_DAYS = {10: 3, 20: 7, 30: 15, 40: 30, 50: 60}


async def get_config(session: AsyncSession) -> SlaConfig:
    """读取全局配置（不存在则创建默认行，id 固定为 1）。"""
    row = await session.get(SlaConfig, 1)
    if row is None:
        row = SlaConfig(id=1)
        session.add(row)
        await session.flush()
    return row


async def load_policies(session: AsyncSession) -> dict[int, SlaPolicy]:
    """按等级加载策略（键为漏洞等级码）。"""
    rows = (await session.execute(select(SlaPolicy))).scalars().all()
    return {r.level: r for r in rows}


# 配置形态：写路径用 ORM 行（`get_config`），读路径用快照（`runtime`）
ConfigLike = SlaConfig | SlaRuntime


def level_days(level: int, config: ConfigLike, policies: dict[int, SlaPolicy]) -> int | None:
    """某等级的时限天数；返回 None 表示该等级不适用 SLA。"""
    if not config.enabled:
        return None
    policy = policies.get(level)
    if policy is None:
        return max(int(config.default_days or 0), 1)
    if not policy.enabled:
        return None
    return max(int(policy.days or 0), 1)


def add_days(start: datetime, days: int, config: ConfigLike) -> datetime:
    """按配置口径顺延 N 天（自然日 / 工作日）。"""
    days = max(int(days or 0), 0)
    if days == 0:
        return start
    if (config.day_basis or "natural") != "workday":
        return start + timedelta(days=days)

    workdays = set(config.workdays or [])
    if not workdays:
        workdays = {0, 1, 2, 3, 4}
    holidays = {str(h) for h in (config.holidays or [])}
    cur = start
    added = 0
    for _ in range(_MAX_STEPS):
        cur = cur + timedelta(days=1)
        if cur.weekday() in workdays and cur.date().isoformat() not in holidays:
            added += 1
            if added >= days:
                return cur
    logger.warning("SLA 工作日推进达到上限（days=%s holidays=%s）", days, len(holidays))
    return cur


def compute_due_at(
    level: int, start: datetime, config: ConfigLike, policies: dict[int, SlaPolicy],
) -> datetime | None:
    """按等级与策略计算截止时间；SLA 关闭或该等级不适用时返回 None。"""
    days = level_days(level, config, policies)
    if days is None:
        return None
    return add_days(start, days, config)


def apply_to_vul(vul: Vul, config: ConfigLike, policies: dict[int, SlaPolicy]) -> None:
    """把当前策略应用到漏洞（新增 / 等级变更 / 重算时调用）。"""
    base = vul.submit_time or tznow()
    vul.due_at = compute_due_at(int(vul.level or 30), base, config, policies)


def is_closed(vul: Vul, config: ConfigLike) -> bool:
    """漏洞是否已停止计时（状态命中配置的 stop_statuses）。"""
    return int(vul.status or 0) in {int(s) for s in (config.stop_statuses or [20, 60])}


def evaluate(vul: Vul, config: ConfigLike, nowt: datetime | None = None) -> dict:
    """漏洞 SLA 派生状态：{due_at, sla_state, sla_remaining_hours, sla_overdue_days}。"""
    nowt = nowt or tznow()
    due = vul.due_at
    if due is None:
        return {
            "due_at": None, "sla_state": "none",
            "sla_remaining_hours": None, "sla_overdue_days": None,
        }
    remaining = (due - nowt).total_seconds() / 3600.0
    if is_closed(vul, config):
        state = "closed"
    elif remaining < 0:
        state = "overdue"
    elif remaining <= warn_hours(config):
        state = "due_soon"
    else:
        state = "ok"
    return {
        "due_at": due,
        "sla_state": state,
        "sla_remaining_hours": round(remaining, 2),
        "sla_overdue_days": round(max(0.0, -remaining) / 24.0, 2),
    }


def enrich(vul: Vul, config: ConfigLike, nowt: datetime | None = None) -> None:
    """把派生字段挂到 ORM 实例上（供 VulOut 的 model_validate 读取，不落库）。"""
    for key, value in evaluate(vul, config, nowt).items():
        setattr(vul, key, value)


def warn_hours(config: ConfigLike) -> float:
    value = config.warn_hours if config.warn_hours is not None else DEFAULT_WARN_HOURS
    return max(float(value), 0.0)


def stop_statuses(config: ConfigLike) -> list[int]:
    return [int(s) for s in (config.stop_statuses or [20, 60])]


def overdue_condition(config: ConfigLike, nowt: datetime | None = None):
    """逾期 SQL 条件（列表 / 看板 / 开放 API 共用）：有截止时间、已过期且未闭环。"""
    nowt = nowt or tznow()
    return (
        Vul.due_at.is_not(None),
        Vul.due_at < nowt,
        Vul.status.notin_(stop_statuses(config)),
    )


def due_soon_condition(config: ConfigLike, nowt: datetime | None = None):
    """即将到期 SQL 条件：未闭环且剩余时间不超过 warn_hours。"""
    nowt = nowt or tznow()
    limit = nowt + timedelta(hours=warn_hours(config))
    return (
        Vul.due_at.is_not(None),
        Vul.due_at >= nowt,
        Vul.due_at <= limit,
        Vul.status.notin_(stop_statuses(config)),
    )


def sla_state_condition(state: str, config: ConfigLike, nowt: datetime | None = None) -> list:
    """按派生状态筛选的 SQL 条件列表（`sla_state=none` 表示无截止时间）。"""
    nowt = nowt or tznow()
    if state == "none":
        return [Vul.due_at.is_(None)]
    if state == "closed":
        return [Vul.due_at.is_not(None), Vul.status.in_(stop_statuses(config))]
    if state == "overdue":
        return list(overdue_condition(config, nowt))
    if state == "due_soon":
        return list(due_soon_condition(config, nowt))
    if state == "ok":
        limit = nowt + timedelta(hours=warn_hours(config))
        return [
            Vul.due_at.is_not(None),
            Vul.due_at > limit,
            Vul.status.notin_(stop_statuses(config)),
        ]
    return []


async def refresh_vulns(
    session: AsyncSession,
    *,
    scope: str = "open",
    config: ConfigLike | None = None,
    policies: dict[int, SlaPolicy] | None = None,
) -> int:
    """历史重算：写回每个漏洞的 due_at。

    `scope=open`（默认）只重算未闭环漏洞，`all` 覆盖全部；返回更新条数。
    """
    config = config or await get_config(session)
    policies = policies if policies is not None else await load_policies(session)
    cond = []
    if scope != "all":
        cond.append(Vul.status.notin_(stop_statuses(config)))
    vulns = (await session.execute(select(Vul).where(*cond))).scalars().all()
    for vul in vulns:
        apply_to_vul(vul, config, policies)
    return len(vulns)


async def collect_reminders(session: AsyncSession, config: ConfigLike) -> list[tuple[Vul, str]]:
    """待提醒清单：[(vul, "sla_due_soon" | "sla_overdue")]，SLA 关闭时返回空。"""
    if not config.enabled:
        return []
    nowt = tznow()
    rows = (
        await session.execute(
            select(Vul)
            .where(Vul.due_at.is_not(None), Vul.status.notin_(stop_statuses(config)))
            .order_by(Vul.due_at)
            .limit(1000)
        )
    ).scalars().all()
    limit = nowt + timedelta(hours=warn_hours(config))
    out: list[tuple[Vul, str]] = []
    for vul in rows:
        if vul.due_at is None:
            continue
        if vul.due_at < nowt:
            out.append((vul, "sla_overdue"))
        elif vul.due_at <= limit:
            out.append((vul, "sla_due_soon"))
    return out


async def sla_stats(
    session: AsyncSession,
    *,
    config: ConfigLike | None = None,
    date_from: str = "",
    date_to: str = "",
    department: str = "",
    source: int | None = None,
    level: int | None = None,
) -> dict:
    """SLA 统计：逾期率、平均修复时长、按等级 / 部门 / 来源分布。

    时间口径复用 `stats_service.vuln_scope_cond`（提交时间半开区间），
    状态口径复用本模块的 `overdue_condition`，保证与列表 / 看板 / 导出一致。
    """
    from app.services import stats_service

    config = config or await get_config(session)
    empty = {
        "enabled": bool(config.enabled), "sla_total": 0, "overdue": 0, "due_soon": 0,
        "overdue_rate": 0.0, "avg_fix_days": None, "avg_overdue_days": None,
        "by_level": [], "by_department": [], "by_source": [],
    }
    if not config.enabled:
        return empty

    nowt = tznow()
    scope_cond = stats_service.vuln_scope_cond(date_from, date_to, source, level, department)
    rows = (
        await session.execute(
            select(
                Vul.id, Vul.level, Vul.status, Vul.due_at, Vul.source,
                Vul.testing_plan_id, Vul.submit_time, Vul.fix_time,
            ).where(*scope_cond)
        )
    ).all()
    # 部门映射取全量工单（不只当前筛选部门）：部门整改排名需要跨部门对比
    plan_dept: dict[int, str] = dict(
        (await session.execute(select(TestingPlan.id, TestingPlan.department))).all()
    )

    stops = set(stop_statuses(config))
    limit = nowt + timedelta(hours=warn_hours(config))

    sla_total = overdue = due_soon = 0
    open_overdue_days: list[float] = []
    fix_days: list[float] = []
    by_level: dict[int, dict] = {}
    by_dept: dict[str, dict] = {}
    by_source: dict[int | None, dict] = {}

    for _vid, lv, status, due, src, plan_id, submit_time, fix_time in rows:
        closed = int(status or 0) in stops
        if fix_time is not None and submit_time is not None and fix_time >= submit_time:
            fix_days.append((fix_time - submit_time).total_seconds() / 86400.0)
        if due is None:
            continue
        sla_total += 1
        lv_agg = by_level.setdefault(
            lv, {"level": lv, "name": VUL_LEVEL.get(lv, str(lv)), "total": 0, "overdue": 0},
        )
        lv_agg["total"] += 1
        src_name = VUL_SOURCE.get(src) if src in VUL_SOURCE else ("渗透测试工单" if plan_id else "未选择")
        src_agg = by_source.setdefault(
            src, {"source": src, "name": src_name, "total": 0, "overdue": 0},
        )
        src_agg["total"] += 1
        dept_name = plan_dept.get(plan_id) or "未关联工单"
        dept_agg = by_dept.setdefault(
            dept_name, {"department": dept_name, "total": 0, "overdue": 0},
        )
        dept_agg["total"] += 1
        if closed:
            continue
        if due < nowt:
            overdue += 1
            lv_agg["overdue"] += 1
            src_agg["overdue"] += 1
            dept_agg["overdue"] += 1
            open_overdue_days.append((nowt - due).total_seconds() / 86400.0)
        elif due <= limit:
            due_soon += 1

    for item in (*by_level.values(), *by_dept.values(), *by_source.values()):
        item["overdue_rate"] = round(item["overdue"] / item["total"] * 100, 1) if item["total"] else 0.0

    return {
        "enabled": True,
        "sla_total": sla_total,
        "overdue": overdue,
        "due_soon": due_soon,
        "overdue_rate": round(overdue / sla_total * 100, 1) if sla_total else 0.0,
        "avg_fix_days": round(sum(fix_days) / len(fix_days), 2) if fix_days else None,
        "avg_overdue_days": (
            round(sum(open_overdue_days) / len(open_overdue_days), 2) if open_overdue_days else None
        ),
        "by_level": sorted(by_level.values(), key=lambda x: x["level"]),
        "by_department": sorted(by_dept.values(), key=lambda x: x["overdue"], reverse=True),
        "by_source": sorted(by_source.values(), key=lambda x: x["total"], reverse=True),
    }
