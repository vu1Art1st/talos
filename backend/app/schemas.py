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


# ---------- 应用 / 资产 ----------
class AppIn(BaseModel):
    name: str
    url: str = ""
    app_type: int = 20
    sec_level: int = 40
    status: int = 10
    group_id: int | None = None
    owner_id: int | None = None
    remark: str = ""


class AppOut(AppIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    create_time: datetime | None = None
    update_time: datetime | None = None


class AssetIn(BaseModel):
    value: str
    asset_type: int = 10
    level: int = 40
    is_open: bool = False
    is_https: bool = False
    app_id: int | None = None
    remark: str = ""


class AssetOut(AssetIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    create_time: datetime | None = None


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
    app_id: int | None = None


class VulOut(VulIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: int = 10
    is_retest: bool = False
    delay_days: int = 0
    delay_reason: str = ""
    submitter_id: int | None = None
    app_name: str = ""
    submit_time: datetime | None = None
    audit_time: datetime | None = None
    notice_time: datetime | None = None
    fix_time: datetime | None = None
    update_time: datetime | None = None


class VulTransitionIn(BaseModel):
    status: int
    comment: str = ""


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
    app_id: int | None = None


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
    summary_html: str = ""
    summary_json: dict | None = None
    status: str = "draft"


class ReportSaveIn(ReportMetaIn):
    version: int = 1
    sections: list[SectionIn] = []


class ReportOut(ReportMetaIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int = 1
    creator_id: int | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None
    sections: list[SectionOut] = []


class ReportListOut(ReportMetaIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int = 1
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
