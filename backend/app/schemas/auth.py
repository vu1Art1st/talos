"""认证与用户域模型：令牌、用户、角色、组织。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
