from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import now as _now
from app.db import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    remark: Mapped[str] = mapped_column(String(255), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"

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
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    role: Mapped[Role | None] = relationship(back_populates="users", lazy="selectin")


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

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=_now)
