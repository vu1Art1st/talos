"""Word 导入域模型：批次、解析记录与确认入库请求。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .common import OptAffectedUrl, OptHtmlStr


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
    # 漏洞等级来源与一致性：detail/summary/template/default；level_mismatch=True 时
    # 导入确认前前端弹窗提醒「风险问题汇总与风险问题详情等级不一致」
    level_source: str = "default"
    level_summary_text: str = ""
    level_detail_text: str = ""
    level_mismatch: bool = False
    status: str = "parsed"
    parse_error: str = ""
    vul_id: int | None = None
    # ---- P1-5 数据治理 ----
    merge_vul_id: int | None = None  # 选择「合并到已有漏洞」时的目标
    outcome: str = ""  # created / updated / merged / skipped / failed
    outcome_reason: str = ""


class ImportRecordUpdateIn(BaseModel):
    title: str | None = None
    vul_type: int | None = None
    level: int | None = None
    # 影响URL：多值与漏洞录入同一口径（切分/去重/上限见 schemas.common.normalize_affected_url）
    affected_url: OptAffectedUrl = None
    description_html: OptHtmlStr = None
    reproduce_html: OptHtmlStr = None
    solution_html: OptHtmlStr = None


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
    record_ids: list[int] | None = None  # None 表示该批次全部解析成功记录（批量确认场景）
    asset_id: int | None = None  # 入库到已有资产
    report_id: int | None = None  # 入库后自动追加为该报告的漏洞章节
    testing_plan_id: int | None = None  # 显式关联测试计划；报告格式未指定时按系统名自动匹配/创建


class BatchConfirmIn(BaseModel):
    batch_ids: list[int]  # 待批量确认的导入批次（服务端去重）
    testing_plan_id: int | None = None  # 统一关联的渗透测试工单
    asset_id: int | None = None  # 统一入库到已有资产（随工单联动默认，可覆盖）


class BatchConfirmItemOut(BaseModel):
    batch_id: int
    filename: str = ""
    status: str = "confirmed"  # confirmed | skipped | failed
    detail: str = ""


class BatchConfirmOut(BaseModel):
    confirmed: int
    skipped: int
    failed: int
    report_ids: list[int] = []  # 本次生成/关联的报告，前端据此调批量导出
    details: list[BatchConfirmItemOut] = []


# ---------- P1-5 数据治理：字段修正流水、重复候选、失败重试 ----------
class ImportRecordChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    record_id: int
    field: str = ""
    old_value: str = ""
    new_value: str = ""
    source: str = "manual"
    username: str = ""
    create_time: datetime | None = None


class ImportDuplicateCandidateOut(BaseModel):
    vul_id: int
    title: str = ""
    level: int = 30
    status: int = 10
    affected_url: str = ""
    testing_plan_id: int | None = None
    ticket_id: str = ""
    similarity: float = 0.0


class ImportDuplicateGroupOut(BaseModel):
    record_id: int
    title: str = ""
    level: int = 30
    affected_url: str = ""
    merge_vul_id: int | None = None
    candidates: list[ImportDuplicateCandidateOut] = []


class ImportRecordMergeIn(BaseModel):
    """合并到已有漏洞（`vul_id`）或取消合并（`vul_id=None` → 保留为独立记录）。"""

    vul_id: int | None = None


class ImportRetryOut(BaseModel):
    batch_id: int
    scope: str = "failed"  # failed（仅失败记录）/ batch（整批重解析）
    retried: int = 0
    resolved: int = 0
    still_failed: int = 0
    msg: str = ""
