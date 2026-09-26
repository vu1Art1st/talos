"""报告模板中心模型（P1-4）。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReportTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    report_type: str = "all"
    version: int = 1
    is_active: bool = False
    original_filename: str = ""
    size_bytes: int = 0
    # 校验通过的锚点清单：[{"index": 0, "desc": "封面装饰"}]
    anchors: list = Field(default_factory=list)
    remark: str = ""
    creator_id: int | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None


class TemplatePublishIn(BaseModel):
    """发布请求：上传成功后即可发布为启用版本。"""

    publish: bool = True
    remark: str = Field("", max_length=500)


class TemplatePreviewOut(BaseModel):
    """试生成结果：返回可下载的导出记录 ID（复用导出下载端点，模板用示例数据）。"""

    url: str = ""
    job_id: int | None = None
    msg: str = ""


class TemplateValidateOut(BaseModel):
    """模板占位符（锚点）校验结果。"""

    ok: bool = False
    missing: list[str] = Field(default_factory=list)
    anchors: list = Field(default_factory=list)
