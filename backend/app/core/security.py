"""JWT 签发与解析（HS256）。

时间统一使用 UTC（aware datetime）：
PyJWT 将 naive datetime 按 UTC 处理，若混入本地时间会产生时区偏差（如 iat 偏大 8 小时）。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings


def create_access_token(user_id: int) -> tuple[str, datetime]:
    """签发访问令牌，返回 (token, 过期时间：UTC)。"""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.jwt_expire_days)
    payload = {"sub": str(user_id), "exp": expires_at, "iat": now}
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, expires_at


def decode_token(token: str) -> int:
    """解析令牌并返回 user_id；无效或过期时抛 jwt.InvalidTokenError。"""
    settings = get_settings()
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    return int(payload["sub"])
