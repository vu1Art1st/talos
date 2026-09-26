"""运营看板视图模型（P1-7）：保存个人视图与部门默认视图（首期不做跨租户隔离）。"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutil import now
from app.db import Base


class DashboardView(Base):
    """看板筛选视图：`scope=personal` 仅本人可见；`scope=department` 作为该部门默认视图。"""

    __tablename__ = "dashboard_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True,
    )
    name: Mapped[str] = mapped_column(String(64))
    # personal / department（见 constants.DASHBOARD_VIEW_SCOPES）
    scope: Mapped[str] = mapped_column(String(16), default="personal")
    # scope=department 时生效：该视图作为此部门的默认视图
    department: Mapped[str] = mapped_column(String(128), default="")
    # 筛选条件快照：{date_from, date_to, department, source, level}
    query: Mapped[dict] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, default=now)
    update_time: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
