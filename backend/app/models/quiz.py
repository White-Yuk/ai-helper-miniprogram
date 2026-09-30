"""题库相关数据模型：请求参数、题目结构、LLM 输出与 API 响应。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

QuestionType = Literal["single", "multiple", "judge", "fill"]
QuestionDifficulty = Literal["easy", "medium", "hard"]
QuizDifficulty = Literal["easy", "mixed", "hard"]


class Option(BaseModel):
    """选项。"""

    key: str = Field(min_length=1, description="选项键，如 A/B/C/D")
    text: str = Field(min_length=1, description="选项内容")

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().upper()


class Question(BaseModel):
    """题目（四种题型共用结构）。

    - single 单选：options 3-4 个，answer 为 1 个选项键
    - multiple 多选：options 3-4 个，answer 为 >=2 个选项键
    - judge 判断：options 为空，answer 为 ["对"] 或 ["错"]
    - fill 填空：options 为空，题干用 ____ 标记空位，answer 为每个空的标准答案
    """

    id: str = Field(min_length=1)
    type: QuestionType
    stem: str = Field(min_length=1, description="题干")
    options: list[Option] = Field(default_factory=list)
    answer: list[str] = Field(min_length=1, description="正确答案；格式随题型变化")
    explanation: str = Field(min_length=1, description="详细讲解")
    knowledge_point: str = Field(min_length=1, description="知识点标签")
    difficulty: QuestionDifficulty = "easy"

    @model_validator(mode="after")
    def validate_judge_answer(self) -> "Question":
        if self.type == "judge" and self.answer not in (["对"], ["错"]):
            raise ValueError('判断题答案必须为 ["对"] 或 ["错"]')
        return self


class QuizGenerateRequest(BaseModel):
    """生成题库请求。"""

    user_input: str = Field(min_length=1, max_length=2000, description="学习内容：一句话 / 一段文本")
    question_count: int = Field(default=5, ge=3, le=10, description="题目数量 3-10")
    difficulty: QuizDifficulty = Field(default="mixed", description="难度：easy / mixed / hard")
    question_types: list[QuestionType] = Field(
        default_factory=lambda: ["single", "multiple", "judge"],
        description="题型组合，可自由搭配",
    )

    @field_validator("user_input")
    @classmethod
    def strip_input(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("输入内容不能为空")
        return value

    @field_validator("question_types")
    @classmethod
    def check_types(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("至少选择一种题型")
        return list(dict.fromkeys(value))  # 去重且保持顺序


class QuizData(BaseModel):
    """LLM 结构化输出：题库内容本体。"""

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    questions: list[Question] = Field(min_length=1)


class QuizGenerateData(BaseModel):
    """题库生成接口的业务数据。"""

    quiz_id: str
    title: str
    summary: str
    questions: list[Question]
