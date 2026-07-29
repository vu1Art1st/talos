"""通用业务字典：按 category 区分的可维护下拉选项（如测试计划-测试类型）。"""
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DictOption(Base):
    __tablename__ = "dict_options"
    __table_args__ = (UniqueConstraint("category", "name", name="uq_dict_category_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(64))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
