"""当前用户信息接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.response import success
from app.models.auth import MeData, UserStats
from app.models.user import User
from app.services import record_service

router = APIRouter()


@router.get("/me", summary="当前登录用户信息（含续答摘要）")
def me_route(user: User = Depends(get_current_user), session: Session = Depends(get_db)) -> dict:
    return success(
        MeData(
            id=user.id,
            nickname=user.nickname,
            avatar=user.avatar or "",
            stats=UserStats(),  # 统计三宫格：阶段 4 接入真实数据
            continue_learning=record_service.get_continue_summary(session, user.id),
        )
    )
