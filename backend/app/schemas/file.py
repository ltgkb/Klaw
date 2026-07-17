"""文件工作区 Pydantic 模型。对齐 PRD 6.7。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileRead(BaseModel):
    """文件元信息响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    file_size: int
    content_type: str
    created_at: datetime


class FileShareResponse(BaseModel):
    """分享链接响应。"""

    url: str
    expires_hours: int
