"""运营看板视图模型（P1-7）。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.constants import DASHBOARD_VIEW_SCOPES


class DashboardQuery(BaseModel):
    """看板筛选条件快照（与 /dashboard/stats 的查询参数同构）。"""

    date_from: str = ""
    date_to: str = ""
    department: str = ""
    source: int | None = None
    level: int | None = None


class DashboardViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    scope: str = "personal"
    department: str = Field("", max_length=128)
    query: DashboardQuery = Field(default_factory=DashboardQuery)
    is_default: bool = False

    @field_validator("scope")
    @classmethod
    def _check_scope(cls, v: str) -> str:
        if v not in DASHBOARD_VIEW_SCOPES:
            raise ValueError(f"视图类型仅支持 {list(DASHBOARD_VIEW_SCOPES)}")
        return v


class DashboardViewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    scope: str = "personal"
    department: str = ""
    query: dict = Field(default_factory=dict)
    is_default: bool = False
    create_time: datetime | None = None
    update_time: datetime | None = None
