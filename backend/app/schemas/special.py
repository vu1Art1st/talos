"""专项管理域模型：远程检测、测试计划、漏扫基线工单与春耕行动。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants import NONPEN_ITEMS

from .common import ReportBrief, UserBrief, VulBrief


class RemoteTestingIn(BaseModel):
    """远程检测记录（2026-08-14 按通报口径重构，申诉报告改为附件上传）。"""

    system_name: str = Field(min_length=1, max_length=128)
    notice_time: str = ""  # 通报时间（YYYY-MM）
    department: str = ""  # 资产归属
    notified_unit: str = ""  # 被通报单位
    is_external: bool = False  # 是否外部项目
    vuln_name: str = ""  # 漏洞名称
    vuln_type: str = ""  # 漏洞类型
    appeal_status: str = ""  # 申诉状态：''/success/fail
    appeal_method: str = ""  # 申诉方式
    appeal_file_name: str = ""  # 申诉报告附件原始文件名
    appeal_file_path: str = ""  # 附件存储相对路径
    appeal_file_size: int = 0  # 附件大小（字节）


class RemoteTestingOut(RemoteTestingIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    create_time: datetime | None = None
    update_time: datetime | None = None


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
    actual_mandays_override: bool = False  # 实际人天手动修正标志：修正后不再被初测报告自动覆盖
    asset_ids: list[int] = []  # 关联资产ID，编制计划时前置录入
    brief: str = ""
    no_vul_conclusion: str = ""  # 无漏洞闭环测试结论（确认「测试通过」时记录）
    detail: str = ""
    create_nonpen: bool = False  # 是否勾选「创建漏扫基线工单」：同时生成联动漏扫基线工单（共享工单ID）
    nonpen_test_items: list[str] = []  # 勾选的非渗透测试项（baseline/host/web），联动创建时使用


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


class PlanImportResultOut(BaseModel):
    """测试计划导入结果：按 ID 更新、无 ID 新增。"""

    total: int = 0
    created: int = 0
    updated: int = 0
    failed: int = 0
    errors: list[str] = []


class NonpenPlanIn(BaseModel):
    """漏扫基线工单（扫描类测试，与测试计划平级、独立统计）。"""
    system_name: str = Field(min_length=1, max_length=128)
    plan_name: str = ""  # 计划名称，与测试系统区分
    test_type: str = ""
    department: str = ""
    receive_time: str = ""
    ticket_time: str = ""  # 工单提起时间
    ticket_id_manual: str = ""  # 手动指定工单ID，留空由系统按需求接收日期自动生成（与测试计划共享序列）
    asset_ids: list[int] = []  # 关联资产ID
    test_items: list[str] = []  # 勾选的测试项（baseline/host/web），未勾选项置 ignored 不参与统计
    detail: str = ""

    @field_validator("test_items", mode="after")
    @classmethod
    def _check_test_items(cls, v):
        for k in v:
            if k not in NONPEN_ITEMS:
                raise ValueError(f"不支持的测试项：{k}")
        return list(dict.fromkeys(v))  # 去重保序

    @model_validator(mode="after")
    def _require_ticket_source(self):
        """工单ID必须有来源：手动指定工单ID，或填写需求接收日期以便系统自动生成（与测试计划同序列）。"""
        if not self.ticket_id_manual.strip() and not self.receive_time.strip():
            raise ValueError("请填写「需求接收日期」（用于自动生成工单ID），或手动指定工单ID")
        return self


class NonpenPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    system_name: str = ""
    plan_name: str = ""
    test_type: str = ""
    department: str = ""
    receive_time: str = ""
    ticket_time: str = ""
    ticket_seq: int = 0
    ticket_id_manual: str = ""
    ticket_id: str = ""  # 工单ID：YYYYMMDD-N
    asset_ids: list[int] = []
    items: dict = {}  # 测试项状态容器 {key: {status, first_times, retest_times}}
    testing_plan_id: int | None = None  # 联动来源测试计划ID，非空即「联动」计划
    linked: bool = False  # 是否由测试计划联动创建
    actionable: bool = False  # 「可进行」：存在任一非忽略测试项处于可测试状态
    detail: str = ""
    create_time: datetime | None = None
    update_time: datetime | None = None

    @field_validator("asset_ids", mode="before")
    @classmethod
    def _normalize_asset_ids(cls, v):
        return v or []


class NonpenItemTransitionIn(BaseModel):
    """测试项状态流转操作（后端按 NONPEN_ITEM_ACTIONS 白名单校验）。"""
    action: str = Field(pattern=r"^(start|done|direct_done|start_retest|pass|fail|reset)$")


class NonpenItemIgnoreIn(BaseModel):
    """忽略 / 取消忽略测试项。"""
    ignored: bool = True


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


class CompleteNoVulnIn(BaseModel):
    conclusion: str = ""  # 测试结论：记录到计划并写入无漏洞报告，可留空使用默认结论
    generate_report: bool = True  # 是否同步生成「未发现安全漏洞」报告草稿
    title: str = ""  # 报告标题：留空时自动生成「yyyymmdd+测试系统+渗透测试报告（无漏洞）」
