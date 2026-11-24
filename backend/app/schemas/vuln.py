"""漏洞域模型：录入/输出、批量操作、状态流转与复测记录。"""
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants import VUL_LAYER, VUL_LEVEL
from .asset import AssetBrief
from .common import AffectedUrl, HtmlStr, OptHtmlStr

MARKDOWN_MAX_LENGTH = 50_000
MarkdownStr = Annotated[str, Field(max_length=MARKDOWN_MAX_LENGTH)]


class VulIn(BaseModel):
    title: str
    vul_type: int = 75
    level: int = 30
    source: int = 0  # 漏洞来源（0=未选择；关联渗透测试工单时固定为「渗透测试工单」，服务端强制置 0）
    layer: int = 10
    # 影响URL：多值以换行分隔；切分/去重/条数与长度上限见 schemas.common.normalize_affected_url
    affected_url: AffectedUrl = ""
    description_html: HtmlStr = ""
    description_json: dict | None = None
    reproduce_html: HtmlStr = ""
    reproduce_json: dict | None = None
    solution_html: HtmlStr = ""
    solution_json: dict | None = None
    score: float = 0.0
    risk_score: int = 0
    left_risk_score: int = 0
    asset_level: int = 0
    # CVSS 4.0 向量字符串（存量 3.1 继续兼容），空表示未评
    cvss_vector: str = ""
    asset_ids: list[int] = []
    testing_plan_id: int | None = None  # 关联测试计划


class VulOut(VulIn):
    model_config = ConfigDict(from_attributes=True)

    # 输出侧显式退回普通 str：历史数据可能含空格等不合规内容，输出不应再跑写入校验
    # （否则列表/详情接口会因存量脏数据直接 500）
    affected_url: str = ""

    id: int
    status: int = 10
    department: str = ""  # 归属部门（由关联资产聚合，多个用「、」分隔）
    retest_html: str = ""
    retest_json: dict | None = None
    is_retest: bool = False
    delay_days: int = 0
    delay_reason: str = ""
    submitter_id: int | None = None
    # 当前请求用户是否可直接编辑本漏洞（有关联工单时仅认领者，不因管理员角色放行）
    can_edit: bool = False
    assets: list[AssetBrief] = []
    submit_time: datetime | None = None
    audit_time: datetime | None = None
    notice_time: datetime | None = None
    fix_time: datetime | None = None
    update_time: datetime | None = None
    # ---- P1-1 SLA 修复时限（派生字段，与列表/看板/导出共用 sla_service 判定） ----
    due_at: datetime | None = None
    # none / ok / due_soon / overdue / closed（见 constants.SLA_STATES）
    sla_state: str = "none"
    # 剩余小时（已逾期为负）；未设置截止时间时为 None
    sla_remaining_hours: float | None = None
    # 逾期天数（未逾期为 0）
    sla_overdue_days: float | None = None


class VulBatchIn(BaseModel):
    """同一批资产下批量提交多个漏洞。"""

    asset_ids: list[int] = []
    vulns: list[VulIn] = Field(min_length=1)


class VulPushItemIn(BaseModel):
    """远程 Agent 推送的单条漏洞：正文只接收 Markdown。"""

    external_id: str = Field(min_length=1, max_length=191)
    title: str = Field(min_length=1, max_length=255)
    level: int
    vul_type: int = Field(gt=0)
    layer: int = 10
    affected_url: AffectedUrl
    description_md: MarkdownStr
    reproduce_md: MarkdownStr
    solution_md: MarkdownStr
    score: float = Field(default=0.0, ge=0, le=10)
    risk_score: int = Field(default=0, ge=0)
    left_risk_score: int = Field(default=0, ge=0)
    asset_level: int = Field(default=0, ge=0)
    cvss_vector: str = Field(default="", max_length=255)
    asset_ids: list[int] = []

    @field_validator("external_id", "title")
    @classmethod
    def _strip_required_text(_cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("level")
    @classmethod
    def _valid_level(_cls, value: int) -> int:
        if value not in VUL_LEVEL:
            raise ValueError("非法漏洞等级")
        return value

    @field_validator("layer")
    @classmethod
    def _valid_layer(_cls, value: int) -> int:
        if value not in VUL_LAYER:
            raise ValueError("非法漏洞层级")
        return value

    @field_validator("affected_url")
    @classmethod
    def _require_affected_url(_cls, value: str) -> str:
        if not value.strip():
            raise ValueError("影响URL不能为空")
        return value

    @field_validator("description_md", "reproduce_md", "solution_md")
    @classmethod
    def _require_markdown(_cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Markdown 正文不能为空")
        return value

    @field_validator("asset_ids")
    @classmethod
    def _dedupe_asset_ids(_cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))


class VulPushIn(BaseModel):
    """指定工单的批量漏洞推送请求。"""

    source_system: str = Field(min_length=1, max_length=64)
    items: list[VulPushItemIn] = Field(min_length=1, max_length=100)

    @field_validator("source_system")
    @classmethod
    def _strip_source_system(_cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("来源系统不能为空")
        return value

    @model_validator(mode="after")
    def _unique_external_ids(self):
        ids = [item.external_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("同一批次内 external_id 不能重复")
        return self


class VulPushItemResultOut(BaseModel):
    external_id: str
    vul_id: int
    result: Literal["created", "duplicated"]


class VulPushSummaryOut(BaseModel):
    created: int
    duplicated: int


class VulPushOut(BaseModel):
    plan_id: int
    summary: VulPushSummaryOut
    items: list[VulPushItemResultOut]


class VulImageUploadOut(BaseModel):
    image_id: str
    url: str
    markdown: str
    sha256: str
    size_bytes: int
    content_type: str
    result: Literal["created", "duplicated"]


class VulBatchDeleteIn(BaseModel):
    """批量删除漏洞。"""

    ids: list[int] = Field(min_length=1)


class VulUpdateIn(VulIn):
    """编辑漏洞：在 VulIn 基础上允许直接调整漏洞状态（下拉选项与 VUL_STATUS 一致）。"""

    status: int | None = None


class VulTransitionIn(BaseModel):
    status: int
    comment: str = ""
    # 复测编辑界面随流转一并提交的复测详情（可选）
    retest_html: OptHtmlStr = None
    retest_json: dict | None = None


class VulDelayIn(BaseModel):
    delay_days: int = Field(gt=0)
    delay_reason: str


class VulFieldsIn(BaseModel):
    """报告编辑页漏洞字段下拉框快捷调整：各字段可选，仅更新传入项。"""

    status: int | None = None
    level: int | None = None
    vul_type: int | None = None
    layer: int | None = None


class VulRetestRecordIn(BaseModel):
    """复测处理页的单条复测记录（漏洞修复富文本）。

    title 可选：用户自定义复测记录标题，留空时按创建日期自动生成
    「复测记录yymmdd」（同日多条追加 -1/-2 后缀），便于修改以对应实际复测时间。
    status 可选：创建复测记录时一并调整漏洞状态（复测未修复=50 / 已修复=60），
    选择结论时强制要求 content_html 非空。
    """

    title: str | None = None
    content_html: HtmlStr = ""
    content_json: dict | None = None
    status: int | None = None

    @field_validator("title", mode="after")
    @classmethod
    def _clean_title(_cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class VulRetestRecordOut(VulRetestRecordIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vul_id: int
    username: str = ""
    create_time: datetime | None = None
    update_time: datetime | None = None


class VulLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str = ""
    # 展示名：优先用户姓名（realname），未设置由调用方回退 username（端点批量解析填充）
    realname: str = ""
    action: str = ""
    content: str = ""
    create_time: datetime | None = None
