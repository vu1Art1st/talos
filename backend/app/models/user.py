from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import now as _now
from app.db import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    # P2-1 数据范围：all / department / own / none。拥有 * 的角色始终按 all 处理，
    # 该字段用于其余角色的资源可见范围；缺省 department，禁止无归属用户回退为全量。
    data_scope: Mapped[str] = mapped_column(String(16), default="department", server_default="department")
    remark: Mapped[str] = mapped_column(String(255), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index(
            "uq_users_email_lower",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("email <> ''"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(128))
    realname: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    avatar: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(default=True)
    must_change_password: Mapped[bool] = mapped_column(default=False)
    # 令牌版本号：写入 JWT 载荷并校验；改密/禁用时递增以失效存量 access/refresh 令牌
    token_version: Mapped[int] = mapped_column(default=0)
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"), nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    # 站内消息偏好：{"disabled_types": ["sla"]}。空对象表示全部接收，
    # 新消息类型默认开启，避免每次新增字典都要迁移存量用户。
    message_prefs: Mapped[dict] = mapped_column(
        JSON, default=dict, server_default=text("'{}'::json"),
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    role: Mapped[Role | None] = relationship(back_populates="users", lazy="selectin")
    # P2-1：用户可属于多个组织；组织名称用于兼容既有 department 字符串字段。
    groups: Mapped[list["Group"]] = relationship(
        secondary="group_users",
        lazy="selectin",
    )


class UserSession(Base):
    """可管理的登录会话：JWT access / refresh 均携带稳定 `sid`。

    会话记录落 PostgreSQL，Redis 只继续承担 refresh jti 的一次性轮换状态；
    这样单会话吊销、全部会话吊销与服务重启后的会话可见性都不依赖 Redis 持久性。
    """

    __tablename__ = "user_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True,
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(256), default="")
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class AccountActionToken(Base):
    """邮件改绑 / 密码找回的单次令牌；数据库只保存 SHA-256 摘要。"""

    __tablename__ = "account_action_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True,
    )
    purpose: Mapped[str] = mapped_column(String(32), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    new_email: Mapped[str] = mapped_column(String(128), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now, index=True)
    request_ip: Mapped[str] = mapped_column(String(64), default="")


class PersonalAccessToken(Base):
    """个人访问令牌（PAT）：开放只读 API 认证用，明文仅创建时返回，库中只存 sha256。"""

    __tablename__ = "personal_access_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    # CASCADE：用户删除后其访问令牌一并删除
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64), default="")
    # 明文 token 的 sha256 hex（64 字符），认证时按 hash 查表
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # 明文前缀（前 12 字符）：列表页辨识用，不含敏感部分
    prefix: Mapped[str] = mapped_column(String(16), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    # 令牌 scope（P1-6）：read / plan_write / admin_read / full，见 constants.PAT_SCOPES。
    # 存量令牌默认 full（= 现状能力：读全开、写仍受角色 RBAC 约束），避免兼容性回归。
    scope: Mapped[str] = mapped_column(String(16), default="full", server_default="full")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)

    user: Mapped[User] = relationship(lazy="selectin")


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    # 系统负责人（姓名/电话/邮箱）：供新建资产页下拉选择既有负责人
    owner_name: Mapped[str] = mapped_column(String(64), default="")
    owner_phone: Mapped[str] = mapped_column(String(32), default="")
    owner_email: Mapped[str] = mapped_column(String(128), default="")
    remark: Mapped[str] = mapped_column(String(255), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)


class GroupUser(Base):
    """用户-组多对多关系（沿用洞察2.0 的 GroupUser 设计）。"""

    __tablename__ = "group_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class GroupMember(Base):
    """组织成员：供资产系统负责人下拉选择与组织人员管理。

    取代 Group 表原 owner_name/owner_phone/owner_email 单字段设计，
    一个组织可录入多名成员，资产编辑时从全部成员聚合读取下拉。
    """

    __tablename__ = "group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "name", name="uq_group_member_group_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
