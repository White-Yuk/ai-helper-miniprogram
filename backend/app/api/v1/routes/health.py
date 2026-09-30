"""健康检查接口。"""
from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.core.response import success

router = APIRouter()


@router.get("/health", summary="健康检查")
def health() -> dict:
    settings = get_settings()
    return success(
        {
            "status": "healthy",
            "app_name": settings.app_name,
            "version": settings.version,
        }
    )
