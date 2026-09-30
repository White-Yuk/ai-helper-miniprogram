"""出题 Prompt（版本 v1）。

设计原则（对齐方案设计文档 8.2）：
- 明确题量、题型比例、输出字段
- 讲解通俗简洁、适合小程序阅读
- 禁止输出 Markdown / 额外说明 / 代码块
"""
from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

TYPE_NAMES_CN = {
    "single": "单选题",
    "multiple": "多选题",
    "judge": "判断题",
    "fill": "填空题",
}

DIFFICULTY_CN = {
    "easy": "简单",
    "mixed": "混合",
    "hard": "困难",
}

QUIZ_SYSTEM_PROMPT = (
    "你是一名专业的 AI 学习教练，负责把任意学习内容变成适合小程序闯关答题的题库。\n"
    "你的输出必须是合法 JSON，且只输出 JSON —— 不要输出任何 JSON 之外的内容"
    "（不要 Markdown、不要代码块、不要额外说明）。"
)

QUIZ_USER_TEMPLATE = """请根据以下学习内容生成一组闯关题库。

【学习内容】
{user_input}

【出题要求】
1. 题目总数：{question_count} 题。
2. 难度：{difficulty}。
3. {types_requirement}
4. 每道题必须包含字段：id、type、stem、options、answer、explanation、knowledge_point、difficulty。
5. type 取值说明：
   - single（单选题）：options 为 3-4 个选项；answer 为 1 个选项字母数组，如 ["A"]。
   - multiple（多选题）：options 为 3-4 个选项；answer 为 2 个及以上选项字母数组，如 ["A","C"]。
   - judge（判断题）：options 为空数组 []；answer 必须为 ["对"] 或 ["错"]。
   - fill（填空题）：options 为空数组 []；题干中使用 ____（4 个下划线）标记每个空；answer 为每个空的标准答案数组，如 ["检索"]。
6. id 从 "q1" 开始依次编号；difficulty 取值为 easy / medium / hard；knowledge_point 用简短中文知识点标签。
7. explanation 必须通俗、简洁、适合初学者阅读（60-120 字），不要过度学术化。
8. 题目要覆盖：核心概念理解、易错点辨析、应用场景判断。
9. 如果用户输入内容过短，可以基于常识进行合理补充，但不要偏离主题。

【JSON 输出结构示例】
{{
  "title": "学习主题标题",
  "summary": "本次题库的一两句话摘要",
  "questions": [
    {{
      "id": "q1",
      "type": "single",
      "stem": "题干",
      "options": [{{"key": "A", "text": "选项A"}}, {{"key": "B", "text": "选项B"}}],
      "answer": ["A"],
      "explanation": "详细讲解",
      "knowledge_point": "知识点标签",
      "difficulty": "easy"
    }}
  ]
}}"""


def build_types_requirement(question_types: list[str]) -> str:
    """把题型配置翻译成给模型的中文出题要求。"""
    names = [TYPE_NAMES_CN[t] for t in question_types]
    lines = [f"请生成以下 {len(names)} 种题型：{'、'.join(names)}；每种题型至少出现 1 题。"]
    if "single" in question_types:
        lines.append("单选保证只有一个正确选项。")
    if "multiple" in question_types:
        lines.append("多选至少有两个正确选项。")
    if "judge" in question_types:
        lines.append("判断题表述要有辨析价值，答案必须明确为「对」或「错」。")
    if "fill" in question_types:
        lines.append("填空题每个空只考一个关键词，答案简短唯一。")
    return "\n".join(lines)


def build_quiz_prompt() -> ChatPromptTemplate:
    """返回带变量的出题提示词模板。

    调用方需传入：user_input / question_count / difficulty / types_requirement。
    """
    return ChatPromptTemplate.from_messages(
        [
            ("system", QUIZ_SYSTEM_PROMPT),
            ("user", QUIZ_USER_TEMPLATE),
        ]
    )
