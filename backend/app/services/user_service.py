"""用户服务：按 openid 查/建用户。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.utils.nickname import build_default_nickname


def get_or_create_user_by_openid(session: Session, openid: str) -> tuple[User, bool]:
    """按 openid 查找用户；不存在则创建（默认昵称）。返回 (user, is_new)。"""
    user = session.scalars(select(User).where(User.openid == openid)).one_or_none()
    if user is None:
        user = User(openid=openid, nickname=build_default_nickname(openid))
        session.add(user)
        session.commit()
        session.refresh(user)
        return user, True

    user.last_login_at = datetime.now()
    session.commit()
    return user, False
