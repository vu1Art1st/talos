from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Report(Base):
    """漏洞报告：元信息 + 有序富文本章节。version 用于编辑乐观锁。"""

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
    version: Mapped[int] = mapped_column(Integer, default=1)
    testing_plan_id: Mapped[int | None] = mapped_column(ForeignKey("testing_plans.id"), nullable=True)
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    fmt: Mapped[str] = mapped_column(String(8), default="docx")  # docx / pdf
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending/running/done/failed
    file_path: Mapped[str] = mapped_column(String(512), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finish_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
