"""出题链：ChatPromptTemplate + 结构化输出（QuizData）。"""
from __future__ import annotations

from app.core.config import get_settings
from app.llm.langchain_factory import create_chat_model
from app.models.quiz import QuizData
from app.prompts.quiz_prompt import build_quiz_prompt


def build_quiz_chain():
    """构建出题链：prompt | structured_llm。

    invoke 输入：{"user_input", "question_count", "difficulty", "types_requirement"}
    invoke 输出：QuizData（Pydantic 实例）
    """
    settings = get_settings()
    llm = create_chat_model(temperature=settings.quiz_temperature)
    # DeepSeek 不支持 response_format: json_schema（OpenAI 默认模式），改用 function calling
    structured_llm = llm.with_structured_output(QuizData, method="function_calling")
    return build_quiz_prompt() | structured_llm
