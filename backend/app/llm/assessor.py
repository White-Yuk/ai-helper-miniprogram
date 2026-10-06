"""知识可靠性评估器（出题守卫，对齐 design.md D6）。

- 触发时机：知识获取已启用但无有效内容时，由编排层调用（有资料时不评估）；
- 独立评估（而非嵌入出题）：出题任务惯性下模型倾向自信输出，独立评估环境更易承认"不知道"；
- 单次结构化输出调用 + 1 次轻试重试 + 超时（assessment_timeout_seconds，默认 20s）；
- 最终失败抛异常 → 编排层降级为纯模型出题（等价升级前行为）+ warning 日志。
"""
from __future__ import annotations

import logging
from datetime import date

from langchain_core.prompts import ChatPromptTemplate

from app.core.config import get_settings
from app.llm.langchain_factory import create_chat_model
from app.models.quiz import ReliabilityAssessment

logger = logging.getLogger(__name__)

ASSESSOR_SYSTEM_PROMPT = (
    "你是一名严谨的知识可靠性评估员，负责判断「为某个主题生成题目」是否安全。"
    "你的输出必须是合法 JSON，且只输出 JSON —— 不要输出任何 JSON 之外的内容。"
)

ASSESSOR_USER_TEMPLATE = """今天是 {today}。

用户想学习并出题的主题：
{user_input}

请评估：在没有外部资料的情况下，你对该主题的知识是否可靠（足以出题且不误导学习者）。
评估标准：
1. 常见、通用的知识（教材级概念、成熟技术等）→ 可靠。
2. 如果主题可能是训练数据截止之后出现的新概念、新事件，或你不熟悉、无法确认其含义 → 必须如实报告"不可靠"，不要逞强。
3. 如果用户输入本身就是一段自包含的解释性文本（可以据此出题）→ 可靠。
4. 宁可保守：不确定时必须报"不可靠"。

只输出 JSON：{{"reliable": true 或 false, "reason": "一句话原因"}}"""


def build_assessor_prompt() -> ChatPromptTemplate:
    """返回评估提示词模板（调用方传 user_input / today）。"""
    return ChatPromptTemplate.from_messages(
        [("system", ASSESSOR_SYSTEM_PROMPT), ("user", ASSESSOR_USER_TEMPLATE)]
    )


def _build_assess_chain(settings=None):
    """构建评估链：prompt | structured_llm（低 temperature；超时取 assessment_timeout_seconds）。"""
    settings = settings or get_settings()
    llm = create_chat_model(temperature=0.0, timeout=settings.assessment_timeout_seconds)
    structured = llm.with_structured_output(ReliabilityAssessment, method="function_calling")
    return build_assessor_prompt() | structured


def assess_reliability(user_input: str) -> ReliabilityAssessment:
    """评估模型对主题的知识可靠性（含 1 次轻试重试）；最终失败抛异常交编排层降级。"""
    chain = _build_assess_chain()
    inputs = {"user_input": user_input, "today": date.today().isoformat()}
    last_error: Exception | None = None
    for attempt in range(1, 3):  # 初次 + 1 次轻试重试
        try:
            result = chain.invoke(inputs)
            if not isinstance(result, ReliabilityAssessment):
                raise ValueError("评估输出结构无法解析")
            return result
        except Exception as exc:  # noqa: BLE001 - 失败重试；最终由编排层降级
            last_error = exc
            logger.warning("可靠性评估失败（第 %s/2 次尝试）：%s", attempt, exc)
    raise RuntimeError(f"知识可靠性评估最终失败：{last_error}")
