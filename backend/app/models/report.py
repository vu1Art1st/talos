from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
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
    test_account: Mapped[str] = mapped_column(String(255), default="")  # 被测测试账号（导出模板测试目标表第5行）
    actual_mandays: Mapped[float] = mapped_column(Float, default=0)  # 实际人天（自动计算：结束日期 - 开始日期）
    version: Mapped[int] = mapped_column(Integer, default=1)  # 导出版本：每次导出成功 +1
    revision: Mapped[int] = mapped_column(Integer, default=0)  # 编辑乐观锁：每次保存 +1
    # 生成/保存报告时对关联漏洞 {vul_id: update_time} 的快照，用于再次生成时的相似性判定
    vul_edit_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 复测报告生成时关联漏洞状态快照 {vul_id: {status, retest_html, retest_json}}，
    # 再次发起复测时对比当前漏洞状态，未更新则阻止生成新复测报告
    retest_vul_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 索引（P0-4）：报告列表按更新时间排序、按工单归属筛选（复测三态/报告归集均用到）
    testing_plan_id: Mapped[int | None] = mapped_column(
        ForeignKey("testing_plans.id"), nullable=True, index=True,
    )

    def fingerprint(self) -> dict:
        """报告内容指纹：编辑锁版本 + 报告更新时间 + 关联漏洞编辑时间快照。

        任一维度变化（编辑报告/编辑关联漏洞/导出后版本+1）都会使指纹变化，
        供导出前重复判断与导出任务记录对比。
        """
        return {
            "revision": self.revision,
            "update_time": self.update_time.isoformat() if self.update_time else "",
            "vul_edit_snapshot": self.vul_edit_snapshot,
        }
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    # 索引（P0-4）：报告列表默认按更新时间排序
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now, index=True)

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
    # 导出时的报告内容指纹 {revision, update_time, vul_edit_snapshot}，用于导出前重复判断
    report_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 幂等键（P0-2）：仅自动导出使用（`auto:<批次ID>`），唯一索引保证「同一批次重复确认
    # 不会生成第二条导出记录与第二份文件」；手动导出留 NULL（唯一索引允许多个 NULL）。
    dedup_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # ---- P1-4 报告模板中心：导出所用模板（历史报告可追溯） ----
    # template_id 为空表示使用包内默认模板（settings.REPORT_TEMPLATE）
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("report_templates.id", ondelete="SET NULL"), nullable=True,
    )
    template_version: Mapped[int] = mapped_column(Integer, default=0)
    template_name: Mapped[str] = mapped_column(String(128), default="")
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    finish_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # ---- 任务生命周期（P0-3）：租约 / 心跳 / 重试 / 死信，统一口径见 services/task_lifecycle.py ----
    attempts: Mapped[int] = mapped_column(Integer, default=0)  # 已尝试次数（含当前次）
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 超期即视为孤儿任务；建索引供启动回收扫描按租约过期快速定位
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    dead_letter_reason: Mapped[str] = mapped_column(Text, default="")  # 进死信的原因（永久错误/超次数）


# 自动导出幂等键的唯一索引（显式命名，保证 Alembic 迁移与 create_all 建出同名对象）
Index("uq_export_jobs_dedup_key", ExportJob.dedup_key, unique=True)
