from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import now
from app.db import Base


class Report(Base):
    """漏洞报告：元信息 + 有序富文本章节。revision 用于编辑乐观锁，version 为导出版本号。"""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    project_name: Mapped[str] = mapped_column(String(255), default="")
    customer: Mapped[str] = mapped_column(String(255), default="")
    author: Mapped[str] = mapped_column(String(64), default="")
    test_start: Mapped[str] = mapped_column(String(32), default="")
    test_end: Mapped[str] = mapped_column(String(32), default="")
    target_ip: Mapped[str] = mapped_column(String(255), default="")  # 被测系统 IP，导出模板测试目标表使用
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft / final / completed
    version: Mapped[int] = mapped_column(Integer, default=1)  # 导出版本：每次导出成功 +1
    revision: Mapped[int] = mapped_column(Integer, default=0)  # 编辑乐观锁：每次保存 +1
    testing_plan_id: Mapped[int | None] = mapped_column(ForeignKey("testing_plans.id"), nullable=True)
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)

    sections: Mapped[list["ReportSection"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportSection.order",
        lazy="selectin",
    )


class ReportSection(Base):
    __tablename__ = "report_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    order: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(255), default="")
    content_html: Mapped[str] = mapped_column(Text, default="")
    content_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    vul_id: Mapped[int | None] = mapped_column(ForeignKey("vulns.id"), nullable=True)

    report: Mapped[Report] = relationship(back_populates="sections")


class ExportJob(Base):
    __tablename__ = "export_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")  # 导出时的报告名快照，用于区分初测/复测报告
    fmt: Mapped[str] = mapped_column(String(8), default="docx")  # docx / pdf
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done/failed
    file_path: Mapped[str] = mapped_column(String(512), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    # 目录域是否已自动更新（当前未启用自动更新，恒为 False，前端据此提示手动更新域）
    toc_auto_updated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    finish_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
