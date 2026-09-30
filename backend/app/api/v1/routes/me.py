"""当前用户信息接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.response import success
from app.models.auth import UserPublic
from app.models.user import User

router = APIRouter()


@router.get("/me", summary="当前登录用户信息（后续阶段扩展统计与续答）")
def me_route(user: User = Depends(get_current_user)) -> dict:
    return success(UserPublic(id=user.id, nickname=user.nickname, avatar=user.avatar or ""))
