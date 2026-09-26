from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutil import now
from app.db import Base


class ImportBatch(Base):
    """一次 Word 文档导入批次。"""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    # pending -> parsing -> parsed -> confirmed / failed
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # template: 固定模板；report: 平台报告格式（渗透测试/复测报告）
    doc_kind: Mapped[str] = mapped_column(String(16), default="template")
    # 报告格式解析出的元信息：system_name / report_date / is_retest / target_url / target_ip
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    # ---- 任务生命周期（P0-3）：租约 / 心跳 / 重试 / 死信，口径见 services/task_lifecycle.py ----
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    dead_letter_reason: Mapped[str] = mapped_column(Text, default="")

    records: Mapped[list["ImportRecord"]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", order_by="ImportRecord.seq"
    )


class ImportRecord(Base):
    """从 Word 解析出的单条待确认漏洞记录。"""

    __tablename__ = "import_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(255), default="")
    vul_type: Mapped[int] = mapped_column(Integer, default=75)
    level: Mapped[int] = mapped_column(Integer, default=30)
    # 影响URL：多值以换行分隔存储，用 Text 与 vulns.affected_url 同口径（勿回退为定长列）
    affected_url: Mapped[str] = mapped_column(Text, default="")
    description_html: Mapped[str] = mapped_column(Text, default="")
    reproduce_html: Mapped[str] = mapped_column(Text, default="")
    solution_html: Mapped[str] = mapped_column(Text, default="")
    retest_html: Mapped[str] = mapped_column(Text, default="")  # 报告格式的复测详情
    fixed: Mapped[bool] = mapped_column(Boolean, default=False)  # 报告格式的修复状态
    # 漏洞等级来源追溯：detail（风险问题详情）/ summary（风险问题汇总）/ template（导入模板字段）
    # / default（中危兜底）；level_mismatch 标识汇总表与详情等级不一致，供导入预览提醒
    level_source: Mapped[str] = mapped_column(String(16), default="default")
    level_summary_text: Mapped[str] = mapped_column(String(32), default="")
    level_detail_text: Mapped[str] = mapped_column(String(32), default="")
    level_mismatch: Mapped[bool] = mapped_column(Boolean, default=False)
    # parsed / error / confirmed / discarded
    status: Mapped[str] = mapped_column(String(16), default="parsed")
    parse_error: Mapped[str] = mapped_column(Text, default="")
    vul_id: Mapped[int | None] = mapped_column(ForeignKey("vulns.id"), nullable=True)
    # ---- P1-5 数据治理 ----
    # 重复候选视图中选择「合并到已有漏洞」时写入；确认入库时更新该漏洞而非新建
    merge_vul_id: Mapped[int | None] = mapped_column(ForeignKey("vulns.id"), nullable=True)
    # 入库结果（结果报告口径）：created / updated / merged / skipped / failed
    outcome: Mapped[str] = mapped_column(String(16), default="")
    outcome_reason: Mapped[str] = mapped_column(Text, default="")

    batch: Mapped[ImportBatch] = relationship(back_populates="records")


class ImportRecordChange(Base):
    """导入记录字段修正流水（P1-5）：记录字段、修正前后值与修正人，形成可追溯数据链。"""

    __tablename__ = "import_record_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("import_records.id", ondelete="CASCADE"), index=True,
    )
    field: Mapped[str] = mapped_column(String(32), default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    # 来源：manual（人工修正）/ knowledge（知识库回填）
    source: Mapped[str] = mapped_column(String(16), default="manual")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
