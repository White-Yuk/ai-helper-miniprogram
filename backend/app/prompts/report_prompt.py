"""报告 Prompt（版本 v1）。

输入：主题、题库、作答记录、统计结果；输出：结构化复盘报告文字部分。
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

REPORT_SYSTEM_PROMPT = (
    "你是一名学习复盘教练，负责根据用户本次闯关答题记录生成一份结构化复盘报告。\n"
    "你的输出必须是合法 JSON，且只输出 JSON —— 不要输出任何 JSON 之外的内容。"
)

REPORT_USER_TEMPLATE = """请根据以下信息生成复盘报告。

【学习主题】
{topic}

【题库数据】
{quiz_json}

【作答记录】
{answer_records}

【统计结果】
{score_summary}

【输出要求】
1. 正确率等数字已由系统计算完成，你只需输出文字分析，不要编造或复述错误的数字。
2. 分析必须基于真实答题情况：答错的题目对应薄弱点，答对的题目对应掌握点；不要虚构未出现的问题。
3. 语言风格清晰、鼓励式，但不空泛；总结要适合移动端阅读。
4. three_line_summary 固定输出 3 句。

【JSON 输出结构示例】
{{
  "mastered_points": ["掌握较好的知识点"],
  "weak_points": ["薄弱知识点"],
  "three_line_summary": ["总结句1", "总结句2", "总结句3"],
  "advice": ["下一步建议1", "下一步建议2"],
  "share_quote": "一句可用于分享的学习金句"
}}"""


def build_report_prompt() -> ChatPromptTemplate:
    """返回带变量的报告提示词模板。

    调用方需传入：topic / quiz_json / answer_records / score_summary。
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", REPORT_SYSTEM_PROMPT),
            ("user", REPORT_USER_TEMPLATE),
        ]
    )
