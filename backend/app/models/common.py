"""通用模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    """统一响应结构（用于接口文档展示）。"""

    code: int = 0
    message: str = "ok"
    data: Any | None = None
