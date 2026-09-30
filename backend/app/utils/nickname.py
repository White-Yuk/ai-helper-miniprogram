"""默认昵称生成：基于 openid 稳定派生（同一用户每次一致）。"""
from __future__ import annotations

import hashlib

_PREFIX = "小衰学习家"


def build_default_nickname(openid: str) -> str:
    """生成默认昵称：前缀 + 4 位数字（由 openid 稳定派生）。"""
    digest = hashlib.sha256(openid.encode("utf-8")).hexdigest()
    number = int(digest[:8], 16) % 10000
    return f"{_PREFIX}{number:04d}"
