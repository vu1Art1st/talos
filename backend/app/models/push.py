"""远程漏洞推送与图片记录。

外部漏洞 ID 与站内漏洞分离存储：`vulns` 保持业务实体单一职责，
`vul_external_refs` 负责长期幂等映射；图片单独记录以便上传、引用校验与延迟清理。
"""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import now
from app.db import Base


class VulExternalRef(Base):
    """外部系统漏洞 ID → 站内漏洞的长期幂等映射。"""

    __tablename__ = "vul_external_refs"
    __table_args__ = (
        UniqueConstraint("source_system", "external_id", name="uq_vul_external_ref_source_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    vul_id: Mapped[int] = mapped_column(
        ForeignKey("vulns.id", ondelete="CASCADE"), index=True,
    )
    testing_plan_id: Mapped[int] = mapped_column(
        ForeignKey("testing_plans.id", ondelete="CASCADE"), index=True,
    )
    source_system: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(191))
    payload_hash: Mapped[str] = mapped_column(String(64), default="")
    # 保留原始 Markdown，便于排查转换问题与未来按 converter_version 重放
    source_payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    converter_version: Mapped[str] = mapped_column(String(32), default="markdown-v1")
    first_push_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_push_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    last_operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True,
    )


class VulExternalImage(Base):
    """远程 Agent 上传的漏洞图片记录。

    文件仍落在 `uploads/images/<32位hex>.<ext>`，与现有图片鉴权端点、TRGM 索引和
    报告导出本地化链路保持一致。
    """

    __tablename__ = "vul_external_images"
    __table_args__ = (
        UniqueConstraint(
            "plan_id", "source_system", "sha256", name="uq_vul_external_image_plan_sha",
        ),
        UniqueConstraint(
            "plan_id", "source_system", "external_image_id",
            name="uq_vul_external_image_plan_external",
        ),
        UniqueConstraint("file_name", name="uq_vul_external_image_file_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("testing_plans.id", ondelete="CASCADE"), index=True,
    )
    source_system: Mapped[str] = mapped_column(String(64), index=True)
    external_image_id: Mapped[str | None] = mapped_column(String(191), nullable=True)
    file_name: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(64), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploader_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True,
    )
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_used_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
