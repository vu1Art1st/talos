"""漏洞知识库域模型：模板条目与批量导入。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import HtmlStr


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
