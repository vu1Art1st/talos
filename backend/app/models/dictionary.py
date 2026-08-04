"""通用业务字典：按 category 区分的可维护下拉选项（如测试计划-测试类型）。

漏洞类型（VulnType）单独建表，支持内置类型与用户新增。
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import utcnow
from app.db import Base


class DictOption(Base):
    __tablename__ = "dict_options"
    __table_args__ = (UniqueConstraint("category", "name", name="uq_dict_category_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(64))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class VulnType(Base):
    """漏洞类型字典：内置类型 is_builtin=True 不可删除，自定义类型支持新增。

    code 为字典键值：内置类型保留原编码（10/15/20...），自定义类型从 1000 起递增，
    与内置编码空间分离避免冲突。/meta 返回 {code: name} 保持前端兼容。
    """

    __tablename__ = "vuln_types"
    __table_args__ = (UniqueConstraint("code", name="uq_vuln_type_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(64))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
