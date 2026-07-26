from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class ImportBatch(Base):
    """一次 Word 文档导入批次。"""

    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    # pending -> parsing -> parsed -> confirmed / failed
    status: Mapped[str] = mapped_column(String(16), default="pending")
    total: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

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
    affected_url: Mapped[str] = mapped_column(String(512), default="")
    description_html: Mapped[str] = mapped_column(Text, default="")
    reproduce_html: Mapped[str] = mapped_column(Text, default="")
    solution_html: Mapped[str] = mapped_column(Text, default="")
    # parsed / error / confirmed / discarded
    status: Mapped[str] = mapped_column(String(16), default="parsed")
    parse_error: Mapped[str] = mapped_column(Text, default="")
    vul_id: Mapped[int | None] = mapped_column(ForeignKey("vulns.id"), nullable=True)

    batch: Mapped[ImportBatch] = relationship(back_populates="records")
