"""业务异常定义。"""
from __future__ import annotations


class BizException(Exception):
    """业务异常：由全局异常处理器转换为统一响应结构。

    Args:
        code: 业务错误码（如 4001 题库生成失败）
        message: 用户可读的错误信息
        http_status: HTTP 状态码（默认 400；上游 LLM 失败用 502）
    """

    def __init__(self, code: int, message: str, http_status: int = 400) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)
