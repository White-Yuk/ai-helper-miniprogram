"""ID 生成工具。"""
from __future__ import annotations

import uuid


def new_quiz_id() -> str:
    """生成题库 ID，形如 quiz_a1b2c3d4e5f6。"""
    return f"quiz_{uuid.uuid4().hex[:12]}"
