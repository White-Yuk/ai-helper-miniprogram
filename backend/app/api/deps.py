"""API 公共依赖：当前登录用户（必选 / 可选）。"""
from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.exceptions import BizException
from app.core.security import decode_token
from app.models.user import User


def get_optional_current_user(
    authorization: str | None = Header(default=None, description="Bearer <token>（可选）"),
    session: Session = Depends(get_db),
) -> User | None:
    """解析 Authorization 头，返回当前登录用户。

    - 未携带 Authorization：返回 None（匿名，保留无状态行为）
    - 携带但无效/过期：抛 4003（HTTP 401），避免“过期 token 静默变匿名”造成数据归属混乱
    """
    if not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
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


def get_current_user(user: User | None = Depends(get_optional_current_user)) -> User:
    """要求登录：未登录 / 无效 token 抛 4003（HTTP 401）。"""
    if user is None:
        raise BizException(code=4003, message="请先登录", http_status=401)
    return user
