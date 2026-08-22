from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import now
from app.db import Base


class OperationLog(Base):
    """登录与敏感操作审计日志：action 见 constants.AUDIT_ACTIONS（login_* 前缀为登录事件）。"""

    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # SET NULL：用户删除后审计记录保留（冗余 username 仍可读）
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    # 冗余用户名：用户被删除后审计记录仍可读
    username: Mapped[str] = mapped_column(String(64), default="", index=True)
    action: Mapped[str] = mapped_column(String(64), default="", index=True)
    # 操作对象与附加信息（JSON 字符串），如 {"target": "users/3", "name": "admin"}
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(256), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class NotificationChannel(Base):
    """通知渠道：企业微信/钉钉 webhook 与邮件，订阅 NOTIFY_EVENTS 事件。

    config 按类型存 JSON：webhook 渠道 {"url": str}；邮件渠道 {"recipients": [str]}。
    """

    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    type: Mapped[str] = mapped_column(String(16))  # constants.NOTIFY_CHANNEL_TYPES
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    # 订阅的事件代码列表，取值见 constants.NOTIFY_EVENTS
    events: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(default=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
