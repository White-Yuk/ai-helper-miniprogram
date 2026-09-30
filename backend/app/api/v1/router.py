"""v1 路由汇总。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routes import health, quiz, report

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(quiz.router, tags=["quiz"])
api_router.include_router(report.router, tags=["report"])
