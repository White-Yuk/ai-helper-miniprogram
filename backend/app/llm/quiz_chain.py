"""出题链：ChatPromptTemplate + 结构化输出（QuizData）。"""
from __future__ import annotations

from typing import Literal

from app.core.config import get_settings
from app.llm.langchain_factory import create_chat_model
from app.models.quiz import QuizData
from app.prompts.quiz_prompt import build_quiz_prompt

StructuredMethod = Literal["function_calling", "json_mode"]


def build_quiz_chain(structured_method: StructuredMethod = "function_calling"):
    """构建出题链：prompt | structured_llm。

    invoke 输入：{"user_input", "reference_context", "question_count", "difficulty", "types_requirement"}
    invoke 输出：QuizData（Pydantic 实例）；模型未产出内容时返回 None（空响应）

    Args:
        structured_method: 结构化输出方式。
            - "function_calling"（默认）：工具调用。LangChain 1.x 已默认绑定
              tool_choice 指定 QuizData；DeepSeek 服务端偶发改动下可能返回空响应。
            - "json_mode"：JSON 模式，与工具调用走不同的服务端管线，用作
              空响应时的异构兜底（见 quiz_service.generate_quiz 加固重试）。
    """
    settings = get_settings()
    llm = create_chat_model(temperature=settings.quiz_temperature)
    # DeepSeek 不支持 response_format: json_schema（OpenAI 默认模式），
    # function_calling 为主路径；json_mode 为异构兜底路径
    structured_llm = llm.with_structured_output(QuizData, method=structured_method)
    return build_quiz_prompt() | structured_llm
