"""阶段 5：学习报表与知识掌握详情模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TrendPoint(BaseModel):
    """按天趋势点（无答题的日期 accuracy 为 None）。"""

    date: str  # YYYY-MM-DD
    total: int = 0
    correct: int = 0
    accuracy: int | None = None


class DomainStat(BaseModel):
    """各领域（按闯关）掌握度：累计口径，不受时间范围影响。"""

    quiz_id: str
    name: str
    total: int
    correct: int
    accuracy: int = Field(ge=0, le=100)


class StatsData(BaseModel):
    """GET /me/stats 响应。"""

    range: Literal["week", "month", "all"]
    overall_accuracy: int | None = None
    trend: list[TrendPoint] = Field(default_factory=list)
    domains: list[DomainStat] = Field(default_factory=list)


class KnowledgePointStat(BaseModel):
    """单个知识点的掌握情况。"""

    name: str
    total: int  # 该知识点关联的题目总数
    answered: int  # 已作答数
    correct: int  # 答对数
    accuracy: int  # correct / answered（未作答为 0）
    state: Literal["mastered", "weak", "unlearned"]


class KnowledgeDetailData(BaseModel):
    """GET /knowledge-base/{quiz_id} 响应。"""

    quiz_id: str
    title: str
    accuracy: int  # 该闯关整体正确率（已答题口径）
    total_points: int
    mastered_count: int
    weak_count: int
    unlearned_count: int
    points: list[KnowledgePointStat] = Field(default_factory=list)
