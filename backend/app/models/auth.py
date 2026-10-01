"""登录相关请求 / 响应模型。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """真实微信登录请求。"""

    code: str = Field(min_length=1, max_length=512, description="Taro.login() 返回的 code（5 分钟内有效）")


class DevLoginRequest(BaseModel):
    """开发态模拟登录请求。"""

    device_id: str = Field(min_length=1, max_length=128, description="开发调试用的设备标识（稳定即可）")


class UserPublic(BaseModel):
    """对前端暴露的用户信息。"""

    id: int
    nickname: str
    avatar: str = ""


class LoginData(BaseModel):
    """登录成功返回的数据。"""

    token: str
    expires_at: datetime
    is_new: bool
    user: UserPublic


class UserStats(BaseModel):
    """用户学习统计（阶段 3 接入真实数据，当前返回占位值）。"""

    quiz_count: int = 0
    answered_count: int = 0
    avg_accuracy: int = 0


class ContinueLearning(BaseModel):
    """最近未完成闯关摘要（阶段 3 接入真实数据）。"""

    quiz_id: str
    title: str
    current_index: int
    total: int


class MeData(BaseModel):
    """GET /me 响应数据。"""

    id: int
    nickname: str
    avatar: str = ""
    stats: UserStats = Field(default_factory=UserStats)
    continue_learning: ContinueLearning | None = None
