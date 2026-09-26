"""SLA 时限计算与状态判定单元测试（P1-1 验收口径）。

覆盖验收要求里明确点名的日期边界：
- 自然日口径：周末/闰日照常顺延；
- 工作日口径：跳过 `workdays` 之外的星期与 `holidays`，且**跨月、跨年、闰日**正确；
- 状态判定：ok / due_soon / overdue / closed / none 五态与剩余时长、逾期天数；
- 等级策略回落与「停用某等级」语义；
- 筛选条件（`sla_state_condition`）与统计口径共用同一实现（逾期条件条数）。
"""
from datetime import datetime, timedelta

from app.models import Vul
from app.services.sla_service import SlaRuntime, evaluate, level_days
from app.services import sla_service


def _cfg(**kw) -> SlaRuntime:
    base = dict(
        enabled=True, day_basis="natural", default_days=7, warn_hours=24,
        allow_extend=True, workdays=(0, 1, 2, 3, 4), holidays=(), stop_statuses=(20, 60),
    )
    base.update(kw)
    return SlaRuntime(**base)


# ---------- 自然日 ----------
def test_natural_days_include_weekend():
    """自然日口径：直接按日历天顺延，落在周末也照常。"""
    start = datetime(2026, 9, 25, 10, 0)  # 周五
    assert sla_service.add_days(start, 1, _cfg()) == datetime(2026, 9, 26, 10, 0)  # 周六


def test_natural_days_leap_year():
    """自然日口径跨越闰日（2024-02-29 存在）。"""
    assert sla_service.add_days(datetime(2024, 2, 28, 9, 0), 1, _cfg()) == datetime(2024, 2, 29, 9, 0)


def test_add_zero_days_keeps_moment():
    start = datetime(2026, 9, 25, 10, 0)
    assert sla_service.add_days(start, 0, _cfg()) == start


# ---------- 工作日 ----------
def test_workday_skips_weekend():
    """工作日口径：周五 +1 个工作日 = 下周一（跳过周六周日）。"""
    workday = _cfg(day_basis="workday")
    assert sla_service.add_days(datetime(2026, 9, 25, 10, 0), 1, workday) == datetime(2026, 9, 28, 10, 0)


def test_workday_started_on_weekend():
    """起点落在周末同样从下一个工作日开始计数。"""
    workday = _cfg(day_basis="workday")
    assert sla_service.add_days(datetime(2026, 9, 26, 9, 0), 1, workday) == datetime(2026, 9, 28, 9, 0)


def test_workday_cross_month_and_holiday():
    """工作日口径：跨月正确，且被 `holidays` 命中的日期不计入。"""
    workday = _cfg(day_basis="workday")
    # 周五 +5 个工作日：9/28、9/29、9/30、10/1、10/2 → 跨月到 10-02
    assert sla_service.add_days(datetime(2026, 9, 25, 10, 0), 5, workday) == datetime(2026, 10, 2, 10, 0)
    # 把 9/28（周一）设为节假日 → 顺延一天到 9/29
    with_holiday = _cfg(day_basis="workday", holidays=("2026-09-28",))
    assert sla_service.add_days(datetime(2026, 9, 25, 10, 0), 1, with_holiday) == datetime(2026, 9, 29, 10, 0)


def test_workday_leap_day_is_counted():
    """工作日口径的闰日：2028-02-29（周二）应被计入工作日。"""
    workday = _cfg(day_basis="workday")
    assert sla_service.add_days(datetime(2028, 2, 28, 9, 0), 1, workday) == datetime(2028, 2, 29, 9, 0)


def test_workday_falls_back_to_mon_fri_when_empty():
    """未配置工作日时回落到 周一~周五，绝不死循环或返回原值。"""
    cfg = _cfg(day_basis="workday", workdays=())
    assert sla_service.add_days(datetime(2026, 9, 25, 10, 0), 1, cfg) == datetime(2026, 9, 28, 10, 0)


# ---------- 等级策略 ----------
def test_level_days_fallback_and_disable():
    class _Policy:
        def __init__(self, days: int, enabled: bool = True) -> None:
            self.days = days
            self.enabled = enabled

    cfg = _cfg(default_days=9)
    assert level_days(20, cfg, {}) == 9                          # 未配置等级 → 默认时限
    assert level_days(20, cfg, {20: _Policy(5)}) == 5            # 已配置等级 → 该等级时限
    assert level_days(20, cfg, {20: _Policy(5, enabled=False)}) is None  # 停用等级 → 不适用 SLA
    assert level_days(20, _cfg(enabled=False), {20: _Policy(5)}) is None  # SLA 关闭 → 全量不适用


def test_level_days_never_below_one():
    """时限下限为 1 天：配置 0/负数不应产生「立即逾期」的截止时间。"""
    class _Policy:
        def __init__(self, days: int) -> None:
            self.days = days
            self.enabled = True

    assert level_days(20, _cfg(default_days=0), {}) == 1
    assert level_days(20, _cfg(), {20: _Policy(-3)}) == 1


# ---------- 状态判定 ----------
def _vul(level: int = 20, status: int = 30, due_at: datetime | None = None) -> Vul:
    vul = Vul(title="SLA 判定用例", level=level, status=status)
    vul.due_at = due_at
    return vul


def test_evaluate_none_without_due_at():
    info = evaluate(_vul(), _cfg())
    assert info == {
        "due_at": None, "sla_state": "none",
        "sla_remaining_hours": None, "sla_overdue_days": None,
    }


def test_evaluate_ok_due_soon_overdue():
    """同一实现产出 ok / due_soon / overdue 三态与剩余时长、逾期天数。"""
    nowt = datetime(2026, 9, 26, 10, 0)
    cfg = _cfg(warn_hours=24)

    ok = evaluate(_vul(due_at=nowt + timedelta(hours=100)), cfg, nowt)
    assert ok["sla_state"] == "ok"
    assert ok["sla_remaining_hours"] == 100.0
    assert ok["sla_overdue_days"] == 0

    soon = evaluate(_vul(due_at=nowt + timedelta(hours=12)), cfg, nowt)
    assert soon["sla_state"] == "due_soon"

    overdue = evaluate(_vul(due_at=nowt - timedelta(hours=48)), cfg, nowt)
    assert overdue["sla_state"] == "overdue"
    assert overdue["sla_remaining_hours"] == -48.0
    assert overdue["sla_overdue_days"] == 2.0


def test_evaluate_closed_takes_precedence_over_overdue():
    """闭环状态优先于逾期：已修复/已忽略的漏洞不再计入逾期。"""
    nowt = datetime(2026, 9, 26, 10, 0)
    cfg = _cfg()
    for status in (20, 60):
        info = evaluate(_vul(status=status, due_at=nowt - timedelta(days=5)), cfg, nowt)
        assert info["sla_state"] == "closed"


def test_evaluate_boundary_exactly_at_due():
    """恰好等于截止时间算「即将到期」，不算逾期（半开区间口径）。"""
    nowt = datetime(2026, 9, 26, 10, 0)
    info = evaluate(_vul(due_at=nowt), _cfg(warn_hours=24), nowt)
    assert info["sla_state"] == "due_soon"


# ---------- 筛选条件（列表 / 看板 / 开放 API 同源） ----------
def test_sla_state_condition_shapes():
    cfg = _cfg()
    assert len(sla_service.sla_state_condition("none", cfg)) == 1
    assert len(sla_service.sla_state_condition("overdue", cfg)) == 3
    assert len(sla_service.sla_state_condition("due_soon", cfg)) == 4
    assert len(sla_service.sla_state_condition("ok", cfg)) == 3
    assert len(sla_service.sla_state_condition("closed", cfg)) == 2
    assert sla_service.sla_state_condition("unknown-state", cfg) == []


def test_stop_statuses_configurable():
    """停止计时状态可配置：自定义后 `closed` 筛选与判定同步变化。"""
    cfg = _cfg(stop_statuses=(60,))
    assert sla_service.stop_statuses(cfg) == [60]
    nowt = datetime(2026, 9, 26, 10, 0)
    assert evaluate(_vul(status=20, due_at=nowt - timedelta(days=1)), cfg, nowt)["sla_state"] == "overdue"
