"""报告模板中心模型（P1-4）。

设计要点：
- 一个模板名称下可有多个版本（`name + version` 唯一）；
- **同一名称同一时刻只有一个启用版本**（服务层保证）：发布新版本会停用旧版本；
  回滚 = 重新启用旧版本，禁止直接覆盖正在使用的文件；
- 无任何启用模板时导出回退到包内 `report_template.docx`（`settings.REPORT_TEMPLATE`）。
"""
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import now
from app.db import Base


class ReportTemplate(Base):
    """报告 Word 模板（按名称 + 版本保存，`file_path` 为 storage 相对路径）。"""

    __tablename__ = "report_templates"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_report_template_name_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    # penetration（渗透测试报告）/ retest（复测报告）/ all（通用）
    report_type: Mapped[str] = mapped_column(String(16), default="all")
    version: Mapped[int] = mapped_column(Integer, default=1)
    # 同一名称同一时刻仅一个启用版本；启用版本参与导出模板选择
    is_active: Mapped[bool] = mapped_column(default=False)
    file_path: Mapped[str] = mapped_column(String(512), default="")
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # 校验通过的模板锚点清单（表序号 → 说明），供界面展示与缺失提示
    anchors: Mapped[list] = mapped_column(JSON, default=list)
    remark: Mapped[str] = mapped_column(Text, default="")
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
