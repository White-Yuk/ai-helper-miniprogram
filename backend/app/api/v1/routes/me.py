"""当前用户信息接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.response import success
from app.models.auth import MeData, UserStats
from app.models.user import User

router = APIRouter()


@router.get("/me", summary="当前登录用户信息（含统计与续答占位，后续阶段接入真实数据）")
def me_route(user: User = Depends(get_current_user)) -> dict:
    return success(
        MeData(
            id=user.id,
            nickname=user.nickname,
            avatar=user.avatar or "",
            stats=UserStats(),
            continue_learning=None,
        )
    )
