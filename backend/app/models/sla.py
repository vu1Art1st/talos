"""SLA 修复时限模型（P1-1）。

三张表分工：
- `SlaConfig`：全局策略开关与默认口径（单行，id 固定为 1）；
- `SlaPolicy`：按漏洞等级的时限（等级 → 天数），未配置等级回落到 `default_days`；
- `SlaExtension`：延期流水，记录原/新到期时间、原因与操作人（不允许无痕改期）。

到期时间 `Vul.due_at` 由 `services/sla_service.py` 在漏洞新增 / 等级变更时计算落库；
列表、看板、导出、开放 API 共用同一判定函数，不在前端或路由里另行推演。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import now
from app.db import Base

# 默认工作日（周一=0 … 周日=6）：排除周末
DEFAULT_WORKDAYS = [0, 1, 2, 3, 4]
# 默认停止计时状态：已忽略(20) / 已修复(60)，与 constants.VulStatus 数值口径一致
DEFAULT_STOP_STATUSES = [20, 60]


class SlaConfig(Base):
    """SLA 全局配置（单行）。`enabled=False` 时全部漏洞不设到期时间。"""

    __tablename__ = "sla_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    # natural（自然日）/ workday（工作日，排除 workdays 之外的星期与 holidays 中的日期）
    day_basis: Mapped[str] = mapped_column(String(16), default="natural")
    # 未单独配置等级策略时的默认时限（天）
    default_days: Mapped[int] = mapped_column(Integer, default=7)
    # 到期前提醒提前量（小时）
    warn_hours: Mapped[int] = mapped_column(Integer, default=24)
    # 是否允许延期（关闭后延期接口 400）
    allow_extend: Mapped[bool] = mapped_column(default=True)
    # 工作日口径：星期序号列表（0=周一）
    workdays: Mapped[list] = mapped_column(JSON, default=lambda: list(DEFAULT_WORKDAYS))
    # 节假日：["2026-10-01", ...]，仅 workday 口径生效
    holidays: Mapped[list] = mapped_column(JSON, default=list)
    # 停止计时的漏洞状态（进入即视为闭环，不再计入逾期）
    stop_statuses: Mapped[list] = mapped_column(JSON, default=lambda: list(DEFAULT_STOP_STATUSES))
    remark: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class SlaPolicy(Base):
    """按漏洞等级配置的 SLA 时限。"""

    __tablename__ = "sla_policies"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 漏洞等级码（constants.VUL_LEVEL 的键）
    level: Mapped[int] = mapped_column(Integer, unique=True)
    days: Mapped[int] = mapped_column(Integer, default=7)
    enabled: Mapped[bool] = mapped_column(default=True)
    remark: Mapped[str] = mapped_column(String(255), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class SlaExtension(Base):
    """SLA 延期流水（审批留痕）：不允许无痕改期。"""

    __tablename__ = "sla_extensions"

    id: Mapped[int] = mapped_column(primary_key=True)
    vul_id: Mapped[int] = mapped_column(
        ForeignKey("vulns.id", ondelete="CASCADE"), index=True,
    )
    old_due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    new_due_at: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(Text, default="")
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
