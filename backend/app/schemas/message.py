"""站内消息与个人待办模型（P1-2）。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    msg_type: str = "vuln"
    title: str = ""
    content: str = ""
    link: str = ""
    is_read: bool = False
    create_time: datetime | None = None


class MessagePage(BaseModel):
    total: int
    unread: int
    items: list[MessageOut]


class MessageReadIn(BaseModel):
    """按 ID 批量已读；`ids` 为空表示全部已读（兼容既有 `POST /messages/read`）。"""

    ids: list[int] = Field(default_factory=list)


class TodoItemOut(BaseModel):
    category: str
    name: str
    count: int
    items: list[dict] = Field(default_factory=list)


class TodoSummaryOut(BaseModel):
    total: int
    groups: list[TodoItemOut] = Field(default_factory=list)
