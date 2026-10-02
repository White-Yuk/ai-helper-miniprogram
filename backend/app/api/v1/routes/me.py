"""当前用户信息接口：资料、续答、学习报表、头像上传。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.response import success
from app.models.auth import MeData, ProfileUpdateRequest, UserPublic, UserStats
from app.models.user import User
from app.services import record_service, stats_service, user_service
from app.utils import files

router = APIRouter()


def get_avatar_dir() -> Path:
    """依赖注入：头像存储目录（测试中替换为临时目录）。"""
    return files.default_avatar_dir()


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


@router.put("/me", summary="更新用户资料（昵称 / 头像）")
def update_me_route(
    payload: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    updated = user_service.update_profile(session, user, nickname=payload.nickname, avatar=payload.avatar)
    return success(UserPublic(id=updated.id, nickname=updated.nickname, avatar=updated.avatar or ""))


@router.post("/me/avatar", summary="上传头像（JPG/PNG/WebP，≤2MB）")
def upload_avatar_route(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    avatar_dir: Path = Depends(get_avatar_dir),
) -> dict:
    content = file.file.read()
    url = files.save_avatar(content, file.content_type or "", avatar_dir)
    return success({"url": url})


@router.get("/me/stats", summary="学习报表（正确率趋势 / 各领域掌握度）")
def stats_route(
    range_: str = Query(default="week", alias="range", pattern="^(week|month|all)$"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict:
    return success(stats_service.get_user_stats(session, user.id, range_))
