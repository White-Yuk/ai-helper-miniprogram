"""登录接口：真实微信登录 + 开发态模拟登录。"""
from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.exceptions import BizException
from app.core.response import success
from app.core.security import create_access_token
from app.models.auth import DevLoginRequest, LoginData, LoginRequest, UserPublic
from app.models.user import User
from app.services.user_service import get_or_create_user_by_openid
from app.services.wechat_client import WechatCode2SessionError, code2session

logger = logging.getLogger(__name__)

router = APIRouter()


def get_code2session():
    """依赖注入：code2session 调用（测试中通过 dependency_overrides 替换）。"""
    return code2session


def _build_login_data(user: User, is_new: bool) -> LoginData:
    token, expires_at = create_access_token(user.id)
    return LoginData(
        token=token,
        expires_at=expires_at,
        is_new=is_new,
        user=UserPublic(id=user.id, nickname=user.nickname, avatar=user.avatar or ""),
    )


@router.post("/auth/login", summary="微信登录：code 换 openid 后签发 token")
def login_route(
    payload: LoginRequest,
    session: Session = Depends(get_db),
    code2session_func=Depends(get_code2session),
) -> dict:
    try:
        openid = code2session_func(payload.code)
    except WechatCode2SessionError as exc:
        logger.warning("微信登录失败：%s", exc)
        raise BizException(code=4004, message="微信登录失败，请重试", http_status=400) from exc

    user, is_new = get_or_create_user_by_openid(session, openid)
    return success(_build_login_data(user, is_new))


@router.post("/auth/dev-login", summary="开发态模拟登录（仅调试开启时可用）")
def dev_login_route(payload: DevLoginRequest, session: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    if not settings.auth_mock_enabled:
        # 未开启时按“接口不存在”处理，不对外暴露调试入口
        raise BizException(code=4005, message="接口不存在", http_status=404)

    digest = hashlib.sha256(f"device:{payload.device_id}".encode("utf-8")).hexdigest()
    openid = f"mock_{digest[:24]}"
    user, is_new = get_or_create_user_by_openid(session, openid)
    return success(_build_login_data(user, is_new))
