"""漏洞知识库域模型：模板条目与批量导入。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import HtmlStr, Page


class KnowledgeIn(BaseModel):
    """知识库条目：每个漏洞名称至多一条，同一漏洞类型可含多条。"""

    vulnerability_name: str = Field(min_length=1, max_length=255)
    vul_type: int
    severity_level: int = 30
    description_html: HtmlStr = ""
    description_json: dict | None = None
    harm_html: HtmlStr = ""
    harm_json: dict | None = None
    solution_html: HtmlStr = ""
    solution_json: dict | None = None
    references: list[str] = []
    # CVSS 3.1 向量字符串（F4）：套用模板时一并带入漏洞表单的计算器
    cvss_vector: str = ""

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


class KnowledgeSearchItem(BaseModel):
    """跨模板搜索结果条目（轻量）：只带展示与「要不要套用」决策所需字段。

    富文本正文（描述/危害/修复建议/CVSS 向量）由 GET /knowledge/{id} 按需获取，
    避免列表响应被整段 HTML 撑大。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    vulnerability_name: str
    vul_type: int
    # 漏洞类型名称：服务端按 vuln_types 表解析（类型是动态字典，不能用 constants 兜底）
    vul_type_name: str = ""
    severity_level: int = 30
    # 描述（缺失时退危害/修复建议）剥离 HTML 后的纯文本摘要，供列表预览与关键词高亮
    summary: str = ""
    username: str = ""
    update_time: datetime | None = None
    # 命中位置：name（名称/编号）/ references（参考链接）/ content（正文，仅 deep 搜索）
    matched_field: str = ""


class KnowledgeSearchOut(Page[KnowledgeSearchItem]):
    """跨模板全局搜索结果：分页外壳 + 命中条目。"""
