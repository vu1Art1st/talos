"""API 请求/响应模型。"""
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.sanitize import sanitize_html

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


class GroupMemberIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    phone: str = ""
    email: str = ""


class GroupMemberOut(GroupMemberIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    group_id: int


# ---------- 资产 ----------
class PublicUrlItem(BaseModel):
    url: str
    tag: int = 10  # URL_TAG：10 互联网 / 20 办公网


class AssetOwnerItem(BaseModel):
    name: str
    phone: str = ""
    email: str = ""


class PortServiceItem(BaseModel):
    """开放端口与对应服务，成对维护（[端口]:[服务]）。"""

    port: str = ""
    service: str = ""


class NameVersionItem(BaseModel):
    """带版本号的条目（中间件/数据库）。"""

    name: str = ""
    version: str = ""


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    sub_system: str = ""
    department: str = ""
    system_type: str = ""  # 系统类型：自有系统（正式）/自有系统（测试）/DCIT系统 等
    public_urls: list[PublicUrlItem] = []
    internal_urls: list[str] = []
    port_services: list[PortServiceItem] = []
    middlewares: list[NameVersionItem] = []
    databases: list[NameVersionItem] = []
    owners: list[AssetOwnerItem] = []
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


class PlanImportResultOut(BaseModel):
    """测试计划导入结果：按 ID 更新、无 ID 新增。"""

    total: int = 0
    created: int = 0
    updated: int = 0
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

    @field_validator("description_html", "reproduce_html", "solution_html", mode="after")
    @classmethod
    def _clean_html(cls, v: str) -> str:
        return sanitize_html(v)


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
    retest_html: str | None = None
    retest_json: dict | None = None

    @field_validator("retest_html", mode="after")
    @classmethod
    def _clean_html(cls, v: str | None) -> str | None:
        return sanitize_html(v) if v is not None else v


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
    """复测处理页的单条复测记录（漏洞修复富文本）。"""

    content_html: str = ""
    content_json: dict | None = None

    @field_validator("content_html", mode="after")
    @classmethod
    def _clean_html(cls, v: str) -> str:
        return sanitize_html(v)


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


# ---------- 漏洞知识库 ----------
class KnowledgeIn(BaseModel):
    """知识库条目：每个漏洞名称至多一条，同一漏洞类型可含多条。"""

    vulnerability_name: str = Field(min_length=1, max_length=255)
    vul_type: int
    severity_level: int = 30
    description_html: str = ""
    description_json: dict | None = None
    harm_html: str = ""
    harm_json: dict | None = None
    solution_html: str = ""
    solution_json: dict | None = None
    references: list[str] = []

    @field_validator("vulnerability_name", mode="after")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("漏洞名称不能为空")
        return v

    @field_validator("references", mode="after")
    @classmethod
    def _clean_references(cls, v: list[str]) -> list[str]:
        # 去除空白项，仅接受 http/https 链接，避免 javascript: 等危险协议入库
        cleaned = [s.strip() for s in v if s and s.strip()]
        for url in cleaned:
            if not url.lower().startswith(("http://", "https://")):
                raise ValueError(f"参考链接必须以 http:// 或 https:// 开头：{url}")
        return cleaned

    @field_validator("description_html", "harm_html", "solution_html", mode="after")
    @classmethod
    def _clean_html(cls, v: str) -> str:
        return sanitize_html(v)


class KnowledgeBatchIn(BaseModel):
    """批量导入：按漏洞名称 upsert，单次至多 500 条。"""

    items: list[KnowledgeIn] = Field(min_length=1, max_length=500)


class KnowledgeBatchDeleteIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)


class KnowledgeOut(KnowledgeIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str = ""
    create_time: datetime | None = None
    update_time: datetime | None = None


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
    retest_html: str = ""
    fixed: bool = False
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

    @field_validator("description_html", "reproduce_html", "solution_html", mode="after")
    @classmethod
    def _clean_html(cls, v: str | None) -> str | None:
        return sanitize_html(v) if v is not None else v


class ImportBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    doc_kind: str = "template"
    meta_json: dict | None = None
    total: int = 0
    success: int = 0
    failed: int = 0
    error: str = ""
    create_time: datetime | None = None


class ImportConfirmIn(BaseModel):
    record_ids: list[int]
    asset_id: int | None = None  # 入库到已有资产
    report_id: int | None = None  # 入库后自动追加为该报告的漏洞章节
    testing_plan_id: int | None = None  # 显式关联测试计划；报告格式未指定时按系统名自动匹配/创建


# ---------- 报告 ----------
class SectionIn(BaseModel):
    id: int | None = None
    order: int = 0
    title: str = ""
    content_html: str = ""
    content_json: dict | None = None
    vul_id: int | None = None

    @field_validator("content_html", mode="after")
    @classmethod
    def _clean_html(cls, v: str) -> str:
        return sanitize_html(v)


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
    revision: int = 0
    sections: list[SectionIn] = []


class ReportOut(ReportMetaIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int = 1
    revision: int = 0
    testing_plan_id: int | None = None
    creator_id: int | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None
    sections: list[SectionOut] = []


class ReportListOut(ReportMetaIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int = 1
    revision: int = 0
    testing_plan_id: int | None = None
    update_time: datetime | None = None


class ExportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    title: str = ""  # 导出时的报告名快照
    fmt: str
    status: str
    error: str = ""
    create_time: datetime | None = None
    finish_time: datetime | None = None


class ReportVulnStateOut(BaseModel):
    """报告关联漏洞的状态字段视图（报告编辑页下拉框表单与复测编辑面板用）。"""

    vul_id: int
    title: str = ""
    status: int = 10
    level: int = 30
    vul_type: int = 75
    layer: int = 10
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


class ReportBrief(BaseModel):
    """测试计划反向展示已关联报告的摘要视图。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str = "draft"


class RetestRoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    round_no: int
    start_time: datetime | None = None
    done_time: datetime | None = None
    source: str = ""


class TestingPlanIn(BaseModel):
    system_name: str = Field(min_length=1, max_length=128)
    plan_name: str = ""  # 测试计划名称，与测试系统区分
    test_type: str = ""
    department: str = ""
    receive_time: str = ""
    ticket_time: str = ""  # 工单提起时间
    ticket_id_manual: str = ""  # 手动指定的工单ID，留空则由系统按需求接收日期自动生成
    first_test_done_time: str = ""
    status: int = 10  # TESTING_PLAN_STATUS
    retest_notice_time: str = ""
    retest_done_time: str = ""
    stat_critical: int = 0
    stat_high: int = 0
    stat_medium: int = 0
    stat_low: int = 0
    est_mandays: float = 0  # 预估人天
    actual_mandays: float = 0  # 实际人天
    asset_ids: list[int] = []  # 关联资产ID，编制计划时前置录入
    brief: str = ""
    detail: str = ""


class TestingPlanOut(TestingPlanIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_seq: int = 0  # 当日录入次序，配合 receive_time 生成工单ID
    ticket_id: str = ""  # 工单ID：YYYYMMDD-N
    testers: list[UserBrief] = []
    vuls: list[VulBrief] = []
    reports: list[ReportBrief] = []
    retest_rounds: list[RetestRoundOut] = []
    retest_round_count: int = 0
    create_time: datetime | None = None
    update_time: datetime | None = None

    @field_validator("asset_ids", mode="before")
    @classmethod
    def _normalize_asset_ids(cls, v):
        """旧库迁移后 asset_ids 可能为 NULL，归一化为空数组避免序列化失败。"""
        return v or []


class SpringActionIn(BaseModel):
    report_no: str = Field(min_length=1, max_length=128)
    system_name: str = ""
    year: str = ""  # 年度，如 2026
    phase: str = ""  # 阶段，如 第一阶段
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


# ---------- 通用字典 ----------
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
