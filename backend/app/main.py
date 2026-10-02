"""FastAPI 应用入口。

- CORS：开发期允许跨域（可通过 .env 的 CORS_ORIGINS 收紧）
- 统一响应：成功 {code:0, message:"ok", data}；错误由异常处理器统一封装
- 静态资源：/static 提供用户上传文件（头像）访问
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import BizException
from app.core.response import error
from app.utils import files

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="AI 闯关学习小程序后端：题库生成 / 复盘报告生成",
    )

    # 跨域（小程序开发者工具 / H5 调试用）
    # allow_credentials=True：H5 端 Taro.uploadFile 的 XHR 携带凭证模式，
    # 此时浏览器要求响应方反射具体 Origin（不能为 *），Starlette 在 credentials 模式下会自动反射
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 静态资源（用户上传的头像等）
    static_dir = files.BACKEND_DIR / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # 业务路由
    app.include_router(api_router, prefix="/api/v1")

    # ---- 全局异常处理：统一响应结构 ----

    @app.exception_handler(BizException)
    async def handle_biz_exception(request: Request, exc: BizException) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=error(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(item) for item in first.get("loc", []) if item != "body")
        detail = first.get("msg", "参数不合法")
        message = f"参数校验失败：{location} {detail}".strip()
        return JSONResponse(status_code=422, content=error(4000, message))

    return app


app = create_app()
