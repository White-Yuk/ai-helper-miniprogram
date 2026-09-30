"""统一响应结构。"""
from __future__ import annotations

from typing import Any


def success(data: Any = None) -> dict:
    """成功响应：{"code": 0, "message": "ok", "data": ...}"""
    return {"code": 0, "message": "ok", "data": data}


def error(code: int, message: str) -> dict:
    """错误响应体（与统一规范一致）。"""
    return {"code": code, "message": message, "data": None}
