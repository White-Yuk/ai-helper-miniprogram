"""API 公共依赖：当前登录用户。"""
from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import BizException
from app.core.security import decode_token
from app.models.user import User


def get_current_user(
    authorization: str | None = Header(default=None, description="Bearer <token>"),
    session: Session = Depends(get_db),
) -> User:
    """解析 Authorization 头，返回当前登录用户；失败抛 4003（HTTP 401）。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise BizException(code=4003, message="请先登录", http_status=401)

    token = authorization.split(" ", 1)[1].strip()
    try:
        user_id = decode_token(token)
    except Exception:  # noqa: BLE001 - 任何解析失败统一转为登录失效
        raise BizException(code=4003, message="登录已失效，请重新登录", http_status=401) from None

    user = session.get(User, user_id)
    if user is None:
        raise BizException(code=4003, message="登录已失效，请重新登录", http_status=401)
    return user
