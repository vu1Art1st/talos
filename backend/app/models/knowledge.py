from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import now
from app.db import Base


class KnowledgeEntry(Base):
    """漏洞模板库条目：按漏洞名称沉淀标准描述 / 危害说明 / 修复建议模板。

    每个漏洞名称（vulnerability_name）至多一条，同一漏洞类型（constants.VUL_TYPE）
    可包含多条具体漏洞。提交/编辑漏洞时可一键套用，Word 导入确认入库时
    空字段自动回填。富文本沿用 HTML + ProseMirror JSON 双份存储。
    """

    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 漏洞名称：全库唯一，批量导入 upsert 的匹配键
    vulnerability_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    vul_type: Mapped[int] = mapped_column(Integer, index=True)
    # 危害等级：沿用 constants.VUL_LEVEL 字典（10 严重 / 20 高危 / 30 中危 / 40 低危 / 50 安全）
    severity_level: Mapped[int] = mapped_column(Integer, default=30)
    description_html: Mapped[str] = mapped_column(Text, default="")
    description_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    harm_html: Mapped[str] = mapped_column(Text, default="")
    harm_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    solution_html: Mapped[str] = mapped_column(Text, default="")
    solution_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 参考链接：[str]，每项一个 URL
    references: Mapped[list | None] = mapped_column(JSON, default=list)
    creator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str] = mapped_column(String(64), default="")
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
