from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import now
from app.db import Base


class TaskDedupKey(Base):
    """后台任务幂等键（P0-2）。

    队列重试（arq 失败重试 / 进程重启后的恢复投递）可能让同一业务副作用执行两次。
    任务执行前先以幂等键 `INSERT ... ON CONFLICT DO NOTHING` 抢占：抢不到说明该副作用
    已经（或正在）执行，直接返回，不产生第二次通知/导出。

    键由调用方在**业务事件发生时**生成（如通知的一次 dispatch 生成一个 uuid），
    而不是由消息内容派生 —— 后者会把「同分钟内容相同的两次真实事件」误判为重复。
    过期键由 worker 的定期清理任务删除，避免无界增长。
    """

    __tablename__ = "task_dedup_keys"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


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
    # 请求追踪 ID（P1-6）：与 core/log_context 的 X-Request-Id 同值，便于从界面报错定位后端日志；
    # 开放 API 写操作同时把 PAT 名称写入 detail（audit_service 统一补充）
    request_id: Mapped[str] = mapped_column(String(64), default="", index=True)
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


class NotifyDelivery(Base):
    """外部通知投递记录（P1-3）：每条投递的状态、尝试次数、错误与重试计划。

    生命周期：pending --成功--> success；pending --可重试失败--> failed(+next_retry_at)
    --> 重试 ... ；永久错误或超过上限 --> dead（`dead_letter_reason` 留因）。
    投递记录落库而非仅日志：进程重启不丢失待重试记录（worker 的 cron 会按 next_retry_at 重投）。
    """

    __tablename__ = "notify_deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    # SET NULL：渠道删除后投递记录保留（冗余 name/type 仍可读）
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("notification_channels.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    channel_name: Mapped[str] = mapped_column(String(64), default="")
    channel_type: Mapped[str] = mapped_column(String(16), default="")
    event: Mapped[str] = mapped_column(String(32), default="", index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    # 通知正文（重试时按原内容重投，避免"重试内容与首次不一致"）
    content: Mapped[str] = mapped_column(Text, default="")
    # 目标摘要（脱敏）：webhook 仅保留主机名，邮件仅保留域名
    target: Mapped[str] = mapped_column(String(255), default="")
    # pending / success / failed / dead（见 constants.NOTIFY_DELIVERY_STATUS_NAME）
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    http_status: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    dead_letter_reason: Mapped[str] = mapped_column(Text, default="")
    request_time: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finish_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ApiIdempotencyKey(Base):
    """开放 API 写操作幂等键（P1-6）：`Idempotency-Key` 请求头重放返回同一结果。

    键 = `f"{user_id}:{endpoint}:{key}"`；`payload_hash` 不同视为冲突并返回 409；
    过期键由 worker 的定期清理任务删除（避免无界增长）。
    """

    __tablename__ = "api_idempotency_keys"

    key: Mapped[str] = mapped_column(String(191), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    endpoint: Mapped[str] = mapped_column(String(128), default="")
    payload_hash: Mapped[str] = mapped_column(String(64), default="")
    status_code: Mapped[int] = mapped_column(Integer, default=200)
    # 首次执行的响应体（JSON 字符串），重放时原样返回
    response: Mapped[str] = mapped_column(Text, default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
