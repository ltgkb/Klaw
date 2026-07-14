"""通用 Pydantic 模型：分页、统一响应。"""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PageParams(BaseModel):
    """分页查询参数。"""
    page: int = 1
    page_size: int = 20


class PageResponse(BaseModel, Generic[T]):
    """分页响应。"""
    items: list[T]
    total: int
    page: int
    page_size: int


class APIResponse(BaseModel, Generic[T]):
    """统一响应封装。"""
    success: bool = True
    message: str = "ok"
    data: T | None = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "ok") -> "APIResponse":
        return cls(success=True, message=message, data=data)

    @classmethod
    def error(cls, message: str, data: Any = None) -> "APIResponse":
        return cls(success=False, message=message, data=data)
