"""系统域 schema：审计日志（F7）、个人访问令牌（F6）、通知渠道（F3）。"""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.constants import NOTIFY_CHANNEL_TYPES, NOTIFY_EVENTS


# ---------- 审计日志（F7） ----------
class OperationLogOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int | None = None
    username: str = ""
    action: str = ""
    detail: str = ""
    ip: str = ""
    user_agent: str = ""
    create_time: datetime


# ---------- 个人访问令牌（F6） ----------
PAT_EXPIRE_DAYS_CHOICES = (7, 30, 90, 365)


class PatCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    expire_days: int = Field(ge=1, le=365)

    @field_validator("expire_days")
    @classmethod
    def _check_choices(cls, v: int) -> int:
        if v not in PAT_EXPIRE_DAYS_CHOICES:
            raise ValueError(f"有效期仅支持 {list(PAT_EXPIRE_DAYS_CHOICES)} 天档位")
        return v


class PatOut(BaseModel):
    id: int
    name: str = ""
    prefix: str = ""
    expires_at: datetime
    last_used_at: datetime | None = None
    is_active: bool = True
    create_time: datetime

    model_config = {"from_attributes": True}


class PatCreatedOut(PatOut):
    """创建响应：token 明文仅此一次返回，之后只存 sha256。"""
    token: str


# ---------- 通知渠道（F3） ----------
class NotifyChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    type: str
    config: dict = Field(default_factory=dict)
    events: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("type")
    @classmethod
    def _check_type(cls, v: str) -> str:
        if v not in NOTIFY_CHANNEL_TYPES:
            raise ValueError(f"不支持的通知渠道类型: {v}")
        return v

    @field_validator("events")
    @classmethod
    def _check_events(cls, v: list[str]) -> list[str]:
        unknown = [e for e in v if e not in NOTIFY_EVENTS]
        if unknown:
            raise ValueError(f"未知的事件代码: {unknown}")
        return v

    @field_validator("config")
    @classmethod
    def _check_config(cls, v: dict, info) -> dict:
        ctype = info.data.get("type")
        if ctype in ("wecom", "dingtalk"):
            if not str(v.get("url") or "").startswith(("http://", "https://")):
                raise ValueError("webhook 地址必须以 http(s):// 开头")
        elif ctype == "email":
            recipients = v.get("recipients")
            if not isinstance(recipients, list) or not recipients:
                raise ValueError("邮件渠道必须配置至少一个收件人邮箱")
        return v


class NotifyChannelOut(BaseModel):
    id: int
    name: str = ""
    type: str = ""
    config: dict = Field(default_factory=dict)
    events: list[str] = Field(default_factory=list)
    is_active: bool = True
    create_time: datetime
    update_time: datetime

    model_config = {"from_attributes": True}
