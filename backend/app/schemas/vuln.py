"""漏洞域模型：录入/输出、批量操作、状态流转与复测记录。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .asset import AssetBrief
from .common import HtmlStr, OptHtmlStr


class VulIn(BaseModel):
    title: str
    vul_type: int = 75
    level: int = 30
    source: int = 0  # 漏洞来源（0=未选择；关联渗透测试工单时固定为「渗透测试工单」，服务端强制置 0）
    layer: int = 10
    affected_url: str = ""
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
    # CVSS 3.1 向量字符串（如 CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H），空表示未评
    cvss_vector: str = ""
    asset_ids: list[int] = []
    testing_plan_id: int | None = None  # 关联测试计划


class VulOut(VulIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: int = 10
    department: str = ""  # 归属部门（由关联资产聚合，多个用「、」分隔）
    retest_html: str = ""
    retest_json: dict | None = None
    is_retest: bool = False
    delay_days: int = 0
    delay_reason: str = ""
    submitter_id: int | None = None
    assets: list[AssetBrief] = []
    submit_time: datetime | None = None
    audit_time: datetime | None = None
    notice_time: datetime | None = None
    fix_time: datetime | None = None
    update_time: datetime | None = None


class VulBatchIn(BaseModel):
    """同一批资产下批量提交多个漏洞。"""

    asset_ids: list[int] = []
    vulns: list[VulIn] = Field(min_length=1)


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
    def _clean_title(cls, v: str | None) -> str | None:
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
    action: str = ""
    content: str = ""
    create_time: datetime | None = None
