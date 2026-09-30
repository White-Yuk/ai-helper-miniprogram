"""报告链：ChatPromptTemplate + 结构化输出（ReportLlmOutput）。"""
from __future__ import annotations

from app.core.config import get_settings
from app.llm.langchain_factory import create_chat_model
from app.models.report import ReportLlmOutput
from app.prompts.report_prompt import build_report_prompt


def build_report_chain():
    """构建报告链：prompt | structured_llm。

    invoke 输入：{"topic", "quiz_json", "answer_records", "score_summary"}
    invoke 输出：ReportLlmOutput（Pydantic 实例）
    """
    settings = get_settings()
    llm = create_chat_model(temperature=settings.report_temperature)
    structured_llm = llm.with_structured_output(ReportLlmOutput)
    return build_report_prompt() | structured_llm
