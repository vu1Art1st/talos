from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class App(Base):
    """应用系统（对应洞察2.0 App 表）。"""

    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    url: Mapped[str] = mapped_column(String(255), default="")
    app_type: Mapped[int] = mapped_column(Integer, default=20)
    sec_level: Mapped[int] = mapped_column(Integer, default=40)
    status: Mapped[int] = mapped_column(Integer, default=10)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Asset(Base):
    """资产（域名 / IP）。"""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(String(255), index=True)
    asset_type: Mapped[int] = mapped_column(Integer, default=10)
    level: Mapped[int] = mapped_column(Integer, default=40)
    is_open: Mapped[bool] = mapped_column(default=False)
    is_https: Mapped[bool] = mapped_column(default=False)
    app_id: Mapped[int | None] = mapped_column(ForeignKey("apps.id"), nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Vul(Base):
    """漏洞记录。富文本统一为 HTML + ProseMirror JSON 双份存储。"""

    __tablename__ = "vulns"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    vul_type: Mapped[int] = mapped_column(Integer, default=75)
    level: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[int] = mapped_column(Integer, default=10, index=True)
    source: Mapped[int] = mapped_column(Integer, default=10)
    layer: Mapped[int] = mapped_column(Integer, default=10)
    affected_url: Mapped[str] = mapped_column(String(512), default="")

    description_html: Mapped[str] = mapped_column(Text, default="")
    description_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reproduce_html: Mapped[str] = mapped_column(Text, default="")
    reproduce_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    solution_html: Mapped[str] = mapped_column(Text, default="")
    solution_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    score: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    left_risk_score: Mapped[int] = mapped_column(Integer, default=0)
    asset_level: Mapped[int] = mapped_column(Integer, default=0)
    is_retest: Mapped[bool] = mapped_column(default=False)
    delay_days: Mapped[int] = mapped_column(Integer, default=0)
    delay_reason: Mapped[str] = mapped_column(Text, default="")

    app_id: Mapped[int | None] = mapped_column(ForeignKey("apps.id"), nullable=True)
    submitter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    submit_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    audit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notice_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fix_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    app: Mapped[App | None] = relationship(lazy="selectin")
    logs: Mapped[list["VulLog"]] = relationship(back_populates="vul", cascade="all, delete-orphan")


class VulLog(Base):
    __tablename__ = "vul_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    vul_id: Mapped[int] = mapped_column(ForeignKey("vulns.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    vul: Mapped[Vul] = relationship(back_populates="logs")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    msg_type: Mapped[str] = mapped_column(String(32), default="vuln")
    title: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    is_read: Mapped[bool] = mapped_column(default=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
