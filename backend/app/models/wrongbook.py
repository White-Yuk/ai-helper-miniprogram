"""阶段 6：错题本模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.quiz import Option, QuestionType


class WrongItem(BaseModel):
    """错题本条目：含完整题目数据，前端可直接重做。"""

    quiz_id: str
    question_id: str
    type: QuestionType
    stem: str
    options: list[Option] = Field(default_factory=list)
    answer: list[str]
    explanation: str
    knowledge_point: str
    wrong_count: int  # 累计错误次数（原始 1 次 + 重做答错次数）
    last_wrong_answers: list[str]  # 最近一次错误作答（用于“上次你填的是…”提示）


class WrongbookData(BaseModel):
    """GET /wrongbook 响应。"""

    total: int
    items: list[WrongItem] = Field(default_factory=list)


class RedoSubmitRequest(BaseModel):
    """POST /wrongbook/redo 请求：提交单次重做结果（追加记录）。"""

    quiz_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    selected_answers: list[str] = Field(default_factory=list)
    is_correct: bool
    duration_ms: int = Field(default=0, ge=0)


class RedoSubmitData(BaseModel):
    """POST /wrongbook/redo 响应。"""

    remaining: int  # 本次提交后，错题本剩余待清理数
