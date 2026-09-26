"""跨域共用的基础模型：泛型分页、富文本消毒类型、各域 Brief 摘要与通用字典。"""
import re
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


# ---------- 影响URL（多值，换行分隔单字段口径） ----------
# 一个漏洞可关联数十条 URL，历史实现用 varchar(512) 存储导致约 20 条即溢出
# （PostgreSQL StringDataRightTruncation → 录入 500），故 DB 列已改为 Text，
# 长度约束下沉到此处统一校验。上限取值兼顾实用与安全：100 条约 6KB，远低于网关限制。
URL_LIST_MAX_COUNT = 100
URL_ITEM_MAX_LENGTH = 2048
# 分隔符：换行（LF/CRLF）与中英文分号
_URL_SPLIT_RE = re.compile(r"[\r\n;；]+")


def normalize_affected_url(raw: str | None) -> str:
    """影响URL 多值的唯一规范化口径：按换行/分号切分 → trim → 去空 → 去重保序 → 换行拼接。

    非法情况抛 ValueError（FastAPI 转为 422 并把文案透出给前端）：
    - 条目数超过 URL_LIST_MAX_COUNT；
    - 单条长度超过 URL_ITEM_MAX_LENGTH；
    - 条目含空白或控制字符（多为从富文本/Excel 误粘的脏数据）。

    None 归一为空串，便于复用同一类型处理「可选」字段。
    """
    items = [part.strip() for part in _URL_SPLIT_RE.split(raw or "")]
    urls = list(dict.fromkeys(item for item in items if item))
    if len(urls) > URL_LIST_MAX_COUNT:
        raise ValueError(f"影响URL 最多 {URL_LIST_MAX_COUNT} 条，当前共 {len(urls)} 条，请分批录入")
    for idx, url in enumerate(urls, start=1):
        if len(url) > URL_ITEM_MAX_LENGTH:
            raise ValueError(
                f"第 {idx} 条影响URL 长度 {len(url)} 超出上限 {URL_ITEM_MAX_LENGTH} 字符"
            )
        if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in url):
            raise ValueError(f"第 {idx} 条影响URL 含空格或非法字符，请修正后再提交")
    return "\n".join(urls)


def _normalize_optional_affected_url(v: str | None) -> str | None:
    """可选变体：None 直通（表示「本次不修改」），其余走同一套规范化与校验。"""
    return None if v is None else normalize_affected_url(v)


# 影响URL 入库字段类型：写入路径（VulIn / ImportRecordUpdateIn / 春耕草稿）必须使用其一。
# 注意：**输出模型不要复用**（历史脏数据会在序列化时被判非法而 500），输出字段用普通 str。
AffectedUrl = Annotated[str, AfterValidator(normalize_affected_url)]
OptAffectedUrl = Annotated[str | None, AfterValidator(_normalize_optional_affected_url)]


class Page(BaseModel, Generic[T]):
    """通用分页响应。

    P1-6 起附带可选的分页元数据（`page`/`size`/`has_more`/`next_cursor`）：
    存量调用方只读 `total`/`items`，新增字段为兼容性扩展；开放 API 在提供 `cursor`
    时继续返回同一结构，`next_cursor` 为下一页游标（None 表示已到末页）。
    """

    total: int
    items: list[T]
    page: int | None = None
    size: int | None = None
    has_more: bool | None = None
    next_cursor: str | None = None


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
    vul_type: int = 75  # 漏洞类型字典码（远程检测等关联方按名称展示）


class ReportBrief(BaseModel):
    """测试计划反向展示已关联报告的摘要视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
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
