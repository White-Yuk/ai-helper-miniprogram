"""报告相关数据模型：作答记录、请求、LLM 输出与 API 响应。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.quiz import Question


class AnswerRecord(BaseModel):
    """单题作答记录（前端本地判题后提交）。"""

    question_id: str = Field(min_length=1)
    selected_answers: list[str] = Field(default_factory=list)
    is_correct: bool
    duration_ms: int = Field(default=0, ge=0, description="答题耗时（毫秒）")


class ReportGenerateRequest(BaseModel):
    """生成复盘报告请求。"""

    quiz_id: str = ""
    topic: str = Field(min_length=1, description="学习主题")
    questions: list[Question] = Field(min_length=1)
    answer_records: list[AnswerRecord] = Field(min_length=1)


class ReportLlmOutput(BaseModel):
    """LLM 结构化输出：纯文字分析（正确率等数字由后端计算，避免模型算错）。"""

    mastered_points: list[str] = Field(min_length=1, description="掌握较好的知识点")
    weak_points: list[str] = Field(default_factory=list, description="薄弱知识点")
    three_line_summary: list[str] = Field(min_length=1, description="知识总结（建议 3 句）")
    advice: list[str] = Field(min_length=1, description="下一步建议")
    share_quote: str = Field(min_length=1, description="分享金句")


class ReportData(ReportLlmOutput):
    """报告接口的业务数据：后端统计 + LLM 文字分析。"""

    accuracy: int = Field(ge=0, le=100, description="正确率（后端计算，0-100）")
