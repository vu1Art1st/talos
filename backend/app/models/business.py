from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import now
from app.db import Base

# 漏洞-资产多对多关联表
vuln_assets = Table(
    "vuln_assets",
    Base.metadata,
    Column("vul_id", ForeignKey("vulns.id", ondelete="CASCADE"), primary_key=True),
    Column("asset_id", ForeignKey("assets.id"), primary_key=True),
    UniqueConstraint("vul_id", "asset_id", name="uq_vuln_asset"),
)


class Asset(Base):
    """资产（系统级，合并原 App 应用与旧域名/IP 资产）。

    JSON 字段约定：
    - public_urls: [{"url": str, "tag": int}]，tag 见 constants.URL_TAG（互联网/办公网）
    - internal_urls: [str]
    - port_services: [{"port": str, "service": str}]，开放端口与对应服务成对维护
    - middlewares: [{"name": str, "version": str}]
    - databases: [{"name": str, "version": str}]
    - owners: [{"name": str, "phone": str, "email": str}]

    ports/services/middleware/database_type 为历史字段，启动时一次性迁移到新 JSON 字段后不再读写。
    """

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    sub_system: Mapped[str] = mapped_column(String(128), default="")
    department: Mapped[str] = mapped_column(String(128), default="")
    system_type: Mapped[str] = mapped_column(String(64), default="")  # 系统类型：自有系统（正式）/自有系统（测试）/DCIT系统等
    public_urls: Mapped[list | None] = mapped_column(JSON, default=list)
    internal_urls: Mapped[list | None] = mapped_column(JSON, default=list)
    ports: Mapped[list | None] = mapped_column(JSON, default=list)  # 历史字段
    services: Mapped[str] = mapped_column(String(255), default="")  # 历史字段
    middleware: Mapped[str] = mapped_column(String(128), default="")  # 历史字段
    database_type: Mapped[str] = mapped_column(String(128), default="")  # 历史字段
    port_services: Mapped[list | None] = mapped_column(JSON, default=list)
    middlewares: Mapped[list | None] = mapped_column(JSON, default=list)
    databases: Mapped[list | None] = mapped_column(JSON, default=list)
    owners: Mapped[list | None] = mapped_column(JSON, default=list)
    sec_level: Mapped[int] = mapped_column(Integer, default=40)
    status: Mapped[int] = mapped_column(Integer, default=10)
    group_id: Mapped[int | None] = mapped_column(ForeignKey("groups.id"), nullable=True)
    remark: Mapped[str] = mapped_column(Text, default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Vul(Base):
    """漏洞记录。富文本统一为 HTML + ProseMirror JSON 双份存储。"""

    __tablename__ = "vulns"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    vul_type: Mapped[int] = mapped_column(Integer, default=75)
    level: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[int] = mapped_column(Integer, default=10, index=True)
    source: Mapped[int] = mapped_column(Integer, default=70)  # 默认「数智化部」
    layer: Mapped[int] = mapped_column(Integer, default=10)
    affected_url: Mapped[str] = mapped_column(String(512), default="")

    description_html: Mapped[str] = mapped_column(Text, default="")
    description_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reproduce_html: Mapped[str] = mapped_column(Text, default="")
    reproduce_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    solution_html: Mapped[str] = mapped_column(Text, default="")
    solution_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retest_html: Mapped[str] = mapped_column(Text, default="")
    retest_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    score: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    left_risk_score: Mapped[int] = mapped_column(Integer, default=0)
    asset_level: Mapped[int] = mapped_column(Integer, default=0)
    is_retest: Mapped[bool] = mapped_column(default=False)
    delay_days: Mapped[int] = mapped_column(Integer, default=0)
    delay_reason: Mapped[str] = mapped_column(Text, default="")

    testing_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("testing_plans.id"), nullable=True, index=True,
    )

    submitter_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    submit_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    audit_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notice_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fix_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    assets: Mapped[list[Asset]] = relationship(secondary=vuln_assets, lazy="selectin")
    logs: Mapped[list["VulLog"]] = relationship(back_populates="vul", cascade="all, delete-orphan")


class VulRetestRecord(Base):
    """漏洞复测记录：复测处理页可为同一漏洞新增多条「漏洞修复」富文本记录。"""

    __tablename__ = "vul_retest_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    vul_id: Mapped[int] = mapped_column(ForeignKey("vulns.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 用户自定义标题；空则聚合时按创建日期自动生成
    content_html: Mapped[str] = mapped_column(Text, default="")
    content_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class VulLog(Base):
    __tablename__ = "vul_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    vul_id: Mapped[int] = mapped_column(ForeignKey("vulns.id"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(64), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)

    vul: Mapped[Vul] = relationship(back_populates="logs")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    msg_type: Mapped[str] = mapped_column(String(32), default="vuln")
    title: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    is_read: Mapped[bool] = mapped_column(default=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
