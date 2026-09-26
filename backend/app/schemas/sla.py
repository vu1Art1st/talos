"""SLA 修复时限域模型（P1-1）。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import SLA_DAY_BASIS, VUL_STATUS

# 到期前提醒 / 逾期升级的默认阈值（小时）——配置项 warn_hours 仅控制「即将到期」
_MAX_DAYS = 3650


def _check_holidays(values: list[str]) -> list[str]:
    for v in values:
        try:
            datetime.strptime(str(v), "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"节假日日期格式应为 YYYY-MM-DD：{v}") from exc
    return [str(v) for v in values]


class SlaConfigIn(BaseModel):
    """SLA 全局策略配置。"""

    enabled: bool = False
    day_basis: str = "natural"
    default_days: int = Field(7, ge=1, le=_MAX_DAYS)
    warn_hours: int = Field(24, ge=0, le=8760)
    allow_extend: bool = True
    workdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])
    holidays: list[str] = Field(default_factory=list)
    stop_statuses: list[int] = Field(default_factory=lambda: [20, 60])
    remark: str = ""

    @field_validator("day_basis")
    @classmethod
    def _check_basis(cls, v: str) -> str:
        if v not in SLA_DAY_BASIS:
            raise ValueError(f"计时口径仅支持 {list(SLA_DAY_BASIS)}")
        return v

    @field_validator("workdays")
    @classmethod
    def _check_workdays(cls, v: list[int]) -> list[int]:
        bad = [x for x in v if x not in range(7)]
        if bad:
            raise ValueError(f"星期序号必须是 0-6（0=周一），非法值：{bad}")
        return sorted(set(v))

    @field_validator("holidays")
    @classmethod
    def _check_holidays(cls, v: list[str]) -> list[str]:
        return _check_holidays(v)

    @field_validator("stop_statuses")
    @classmethod
    def _check_stop_statuses(cls, v: list[int]) -> list[int]:
        bad = [x for x in v if x not in VUL_STATUS]
        if bad:
            raise ValueError(f"停止计时状态非法：{bad}")
        return sorted(set(v))


class SlaConfigOut(SlaConfigIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    updated_by: int | None = None
    update_time: datetime | None = None


class SlaPolicyIn(BaseModel):
    level: int
    days: int = Field(7, ge=1, le=_MAX_DAYS)
    enabled: bool = True
    remark: str = Field("", max_length=255)

    @field_validator("level")
    @classmethod
    def _check_level(cls, v: int) -> int:
        if v not in (10, 20, 30, 40, 50):
            raise ValueError("漏洞等级仅支持 10/20/30/40/50")
        return v


class SlaPolicyOut(SlaPolicyIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    create_time: datetime | None = None
    update_time: datetime | None = None


class SlaExtendIn(BaseModel):
    """延期请求：`new_due_at` 与 `extend_days` 二选一。"""

    new_due_at: str | None = None
    extend_days: int | None = Field(None, ge=1, le=_MAX_DAYS)
    reason: str = Field(min_length=1, max_length=500)


class SlaExtensionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vul_id: int
    old_due_at: datetime | None = None
    new_due_at: datetime
    reason: str = ""
    username: str = ""
    create_time: datetime | None = None


class SlaRecalculateIn(BaseModel):
    """历史重算范围：open（仅未闭环漏洞）/ all（全部漏洞）。"""

    scope: str = "open"

    @field_validator("scope")
    @classmethod
    def _check_scope(cls, v: str) -> str:
        if v not in ("open", "all"):
            raise ValueError("重算范围仅支持 open / all")
        return v


class SlaRecalculateOut(BaseModel):
    refreshed: int
    scope: str
    msg: str = ""
