"""报告域模型：章节、报告元信息、导出任务与相似性检查。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .common import HtmlStr, ReportBrief


class SectionIn(BaseModel):
    id: int | None = None
    order: int = 0
    title: str = ""
    content_html: HtmlStr = ""
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
    revision: int = 0
    sections: list[SectionIn] = []


class ReportOut(ReportMetaIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int = 1
    revision: int = 0
    actual_mandays: float = 0  # 实际人天（自动计算：结束日期 - 开始日期）
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
    actual_mandays: float = 0  # 实际人天（自动计算：结束日期 - 开始日期）
    testing_plan_id: int | None = None
    ticket_id: str = ""  # 关联工单号（由关联渗透测试工单提供，未关联为空）
    ticket_system_name: str = ""  # 关联工单的测试系统名称
    create_time: datetime | None = None
    update_time: datetime | None = None


class ExportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_id: int
    title: str = ""  # 导出时的报告名快照
    fmt: str
    status: str
    error: str = ""
    toc_auto_updated: bool = False  # 目录域是否已自动更新（当前恒为 False，前端据此提示手动更新域）
    create_time: datetime | None = None
    finish_time: datetime | None = None


class ExportCheckIn(BaseModel):
    """导出前重复判断请求：指定导出格式。"""

    fmt: str = "docx"


class ExportCheckOut(BaseModel):
    """导出前重复判断结果：报告内容与最近一次成功导出完全一致则 duplicate=True。

    提示信息附带重复导出的具体内容（报告标题/格式/版本）与已存在记录的时间、状态，
    供前端展示「继续导出 / 取消」确认。
    """

    duplicate: bool = False
    report_id: int | None = None
    report_title: str = ""
    fmt: str = ""
    last_job_id: int | None = None
    last_time: datetime | None = None
    last_status: str = ""
    last_version: int | None = None
    last_file_name: str = ""
    last_file_size: int | None = None


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


class ReportSimilarityIn(BaseModel):
    """再次生成报告前的高度相似性检查请求。"""

    title: str = Field(min_length=1, max_length=255)
    vul_ids: list[int] = []
    testing_plan_id: int | None = None


class ReportSimilarityOut(BaseModel):
    """相似性检查结果：与历史报告在「基础信息 + 所选漏洞最后编辑时间」上完全一致即高度相似。"""

    similar: bool = False
    matched_reports: list[ReportBrief] = []
