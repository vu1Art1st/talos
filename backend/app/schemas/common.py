"""跨域共用的基础模型：泛型分页、富文本消毒类型、各域 Brief 摘要与通用字典。"""
from datetime import datetime
from typing import Annotated, Generic, TypeVar

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.sanitize import sanitize_html

T = TypeVar("T")


def _sanitize_opt(v: str | None) -> str | None:
    return sanitize_html(v) if v is not None else v


# 入库富文本统一消毒类型：所有富文本字段必须使用其一，替代各模型重复的 _clean_html validator
HtmlStr = Annotated[str, AfterValidator(sanitize_html)]
OptHtmlStr = Annotated[str | None, AfterValidator(_sanitize_opt)]


class Page(BaseModel, Generic[T]):
    total: int
    items: list[T]


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    realname: str = ""


class VulBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    level: int = 30
    status: int = 10
    layer: int = 10  # 所在层（网络层级），供春耕行动等关联方聚合展示


class ReportBrief(BaseModel):
    """测试计划反向展示已关联报告的摘要视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str = "draft"
    actual_mandays: float = 0  # 实际人天，供前端计算计划自动人天（取消修正时恢复展示）
    create_time: datetime | None = None


class DictOptionIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    sort: int = 0


class DictOptionOut(DictOptionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str


class VulnTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    sort: int = 0


class VulnTypeOut(VulnTypeIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: int
    is_builtin: bool = False
