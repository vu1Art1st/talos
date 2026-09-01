"""资产域模型：资产录入/输出与导入结果。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    system_type: str = ""  # 系统类型：自有系统（正式）/自有系统（测试）/DICT系统 等
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
