"""阶段 3：答题记录相关请求 / 响应模型。

字段语义（与前端约定）：
- current_index：已答题数（= 续答恢复时的起始题索引）
- records：作答明细（全量提交，服务端幂等覆盖）
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.quiz import Question
from app.models.report import AnswerRecord


class QuizProgressRequest(BaseModel):
    """保存中途进度请求（幂等：以本次提交为准全量覆盖）。"""

    current_index: int = Field(ge=0, description="已答题数（= 恢复时的起始题索引）")
    records: list[AnswerRecord] = Field(default_factory=list, description="已答记录（全量）")


class QuizSubmitRequest(BaseModel):
    """提交完整作答请求。"""

    records: list[AnswerRecord] = Field(default_factory=list, description="完整作答记录")


class QuizProgressData(BaseModel):
    """保存进度响应。"""

    current_index: int = Field(description="服务端裁剪后的已答题数")
    saved_count: int = Field(description="实际保存的记录条数")


class QuizSubmitData(BaseModel):
    """提交作答响应。"""

    quiz_id: str
    status: str = "done"
    answered_count: int


class UnfinishedQuizData(BaseModel):
    """最近未完成闯关：含完整题库与已答记录，前端可直接恢复续答。"""

    quiz_id: str
    title: str
    summary: str = ""
    questions: list[Question]
    current_index: int
    records: list[AnswerRecord]
    total: int
    updated_at: datetime
