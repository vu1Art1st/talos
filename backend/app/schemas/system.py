"""系统域 schema：审计日志（F7）、个人访问令牌（F6）、通知渠道（F3）。"""
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.constants import NOTIFY_CHANNEL_TYPES, NOTIFY_EVENTS
from app.core.outbound import assert_public_url


# ---------- 审计日志（F7） ----------
class OperationLogOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int | None = None
    username: str = ""
    # 展示名：优先用户姓名（realname），未设置由调用方回退 username（端点批量解析填充）
    realname: str = ""
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
            # 出站目标校验（审计 TALOS-2026-003）：除协议外还要求解析结果为公网地址，
            # 阻断「webhook 指向内网/回环/云元数据」的 SSRF；内网中继场景用
            # VP_NOTIFY_HOST_ALLOWLIST 显式放行（见 core/outbound.py）。
            url = assert_public_url(str(v.get("url") or ""), field="webhook 地址")
            v["url"] = url
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
