"""API 请求/响应模型。"""
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    total: int
    items: list[T]


# ---------- 认证 ----------
class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshIn(BaseModel):
    refresh_token: str


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


class UserOption(BaseModel):
    """用户下拉选项（供报告作者等选择器使用，普通登录用户可见）。"""

    id: int
    name: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    realname: str = ""
    email: str = ""
    phone: str = ""
    is_active: bool = True
    must_change_password: bool = False
    role_id: int | None = None
    role_name: str = ""
    permissions: list[str] = []
    create_time: datetime | None = None
    last_login: datetime | None = None


class UserIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str | None = None
    realname: str = ""
    email: str = ""
    phone: str = ""
    is_active: bool = True
    role_id: int | None = None


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    permissions: list[str] = []
    remark: str = ""


class RoleIn(BaseModel):
    name: str
    permissions: list[str] = []
    remark: str = ""


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    remark: str = ""


class GroupIn(BaseModel):
    name: str
    remark: str = ""


# ---------- 资产 ----------
class PublicUrlItem(BaseModel):
    url: str
    tag: int = 10  # URL_TAG：10 互联网 / 20 办公网


class AssetOwnerItem(BaseModel):
    name: str
    phone: str = ""
    email: str = ""


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    sub_system: str = ""
    department: str = ""
    public_urls: list[PublicUrlItem] = []
    internal_urls: list[str] = []
    ports: list[str] = []
    services: str = ""
    middleware: str = ""
    database_type: str = ""
    owners: list[AssetOwnerItem] = []
    sec_level: int = 40
    status: int = 10
    group_id: int | None = None
    remark: str = ""


class AssetOut(AssetIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    create_time: datetime | None = None
    update_time: datetime | None = None


class AssetBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sub_system: str = ""
    department: str = ""


class AssetImportResultOut(BaseModel):
    total: int = 0
    success: int = 0
    failed: int = 0
    errors: list[str] = []


# ---------- 漏洞 ----------
class VulIn(BaseModel):
    title: str
    vul_type: int = 75
    level: int = 30
    source: int = 10
    layer: int = 10
    affected_url: str = ""
    description_html: str = ""
    description_json: dict | None = None
    reproduce_html: str = ""
    reproduce_json: dict | None = None
    solution_html: str = ""
    solution_json: dict | None = None
    score: int = 0
    risk_score: int = 0
    left_risk_score: int = 0
    asset_level: int = 0
    asset_ids: list[int] = []
    testing_plan_id: int | None = None  # 关联测试计划


class VulOut(VulIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: int = 10
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


class VulTransitionIn(BaseModel):
    status: int
    comment: str = ""
    # 复测编辑界面随流转一并提交的复测详情（可选）
    retest_html: str | None = None
    retest_json: dict | None = None


class VulDelayIn(BaseModel):
    delay_days: int = Field(gt=0)
    delay_reason: str


class VulLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str = ""
    action: str = ""
    content: str = ""
    create_time: datetime | None = None


# ---------- Word 导入 ----------
class ImportRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seq: int
    title: str = ""
    vul_type: int = 75
    level: int = 30
    affected_url: str = ""
    description_html: str = ""
    reproduce_html: str = ""
    solution_html: str = ""
    status: str = "parsed"
    parse_error: str = ""
    vul_id: int | None = None


class ImportRecordUpdateIn(BaseModel):
    title: str | None = None
    vul_type: int | None = None
    level: int | None = None
    affected_url: str | None = None
    description_html: str | None = None
    reproduce_html: str | None = None
    solution_html: str | None = None


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    total: int = 0
    success: int = 0
    failed: int = 0
    error: str = ""
    create_time: datetime | None = None


class ImportConfirmIn(BaseModel):
    record_ids: list[int]
    asset_id: int | None = None
    report_id: int | None = None  # 入库后自动追加为该报告的漏洞章节


# ---------- 报告 ----------
class SectionIn(BaseModel):
    id: int | None = None
    order: int = 0
    title: str = ""
    content_html: str = ""
    content_json: dict | None = None
    vul_id: int | None = None


class SectionOut(SectionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int


class ReportMetaIn(BaseModel):
    title: str
    project_name: str = ""
    customer: str = ""
    author: str = ""
    test_start: str = ""
    test_end: str = ""
    target_ip: str = ""
    status: str = "draft"


class ReportSaveIn(ReportMetaIn):
    version: int = 1
    sections: list[SectionIn] = []


class ReportOut(ReportMetaIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int = 1
    testing_plan_id: int | None = None
    creator_id: int | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None
    sections: list[SectionOut] = []


class ReportListOut(ReportMetaIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int = 1
    testing_plan_id: int | None = None
    update_time: datetime | None = None


class ExportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    fmt: str
    status: str
    error: str = ""
    create_time: datetime | None = None
    finish_time: datetime | None = None


class ReportVulnStateOut(BaseModel):
    """报告关联漏洞的复测状态视图（复测编辑面板用）。"""

    vul_id: int
    title: str = ""
    status: int = 10
    level: int = 30
    retest_html: str = ""
    retest_json: dict | None = None


# ---------- 专项管理 ----------
class RemoteTestingIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    system_name: str = ""
    test_time: str = ""
    department: str = ""
    appeal_success: bool = False
    appeal_report_id: int | None = None


class RemoteTestingOut(RemoteTestingIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    create_time: datetime | None = None
    update_time: datetime | None = None


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


class TestingPlanIn(BaseModel):
    system_name: str = Field(min_length=1, max_length=128)
    test_type: str = ""
    department: str = ""
    receive_time: str = ""
    first_test_done_time: str = ""
    status: int = 10  # TESTING_PLAN_STATUS
    retest_notice_time: str = ""
    retest_done_time: str = ""
    stat_critical: int = 0
    stat_high: int = 0
    stat_medium: int = 0
    stat_low: int = 0
    brief: str = ""
    detail: str = ""


class TestingPlanOut(TestingPlanIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    testers: list[UserBrief] = []
    vuls: list[VulBrief] = []
    create_time: datetime | None = None
    update_time: datetime | None = None


class SpringActionIn(BaseModel):
    report_no: str = Field(min_length=1, max_length=128)
    system_name: str = ""
    appeal_success: bool = False
    score_deduction: float = 0
    doc_no: str = ""
    vul_ids: list[int] = []


class SpringActionOut(SpringActionIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    vuls: list[VulBrief] = []
    create_time: datetime | None = None
    update_time: datetime | None = None
