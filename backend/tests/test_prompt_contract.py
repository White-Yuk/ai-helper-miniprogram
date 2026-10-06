"""Prompt 契约测试：确保提示词包含业务必需的全部要素。

作用：以后调整提示词时，任何关键要素（JSON 字段、填空题规则、判断题规则等）的丢失都会让测试失败。
"""
from __future__ import annotations

from app.prompts.agent_prompt import build_agent_system_prompt
from app.prompts.quiz_prompt import NO_REFERENCE_CONTEXT, build_quiz_prompt, build_types_requirement
from app.prompts.report_prompt import build_report_prompt


class TestTypesRequirement:
    def test_single_and_fill(self):
        text = build_types_requirement(["single", "fill"])
        assert "单选" in text
        assert "填空" in text
        assert "多选" not in text
        assert "判断" not in text

    def test_all_four(self):
        text = build_types_requirement(["single", "multiple", "judge", "fill"])
        for name in ["单选", "多选", "判断", "填空"]:
            assert name in text

    def test_requires_each_type_at_least_once(self):
        text = build_types_requirement(["single", "multiple"])
        assert "至少" in text  # 明确“每种题型至少出现 1 题”


class TestQuizPromptContract:
    def _render(self) -> str:
        prompt = build_quiz_prompt()
        return prompt.invoke(
            {
                "user_input": "什么是 RAG？",
                "reference_context": NO_REFERENCE_CONTEXT,
                "question_count": "5",
                "difficulty": "混合",
                "types_requirement": build_types_requirement(["single", "multiple", "judge", "fill"]),
            }
        ).to_string()

    def test_contains_user_input(self):
        assert "什么是 RAG？" in self._render()

    def test_contains_json_output_fields(self):
        text = self._render()
        for field in [
            "title",
            "summary",
            "questions",
            "stem",
            "options",
            "answer",
            "explanation",
            "knowledge_point",
            "difficulty",
        ]:
            assert field in text, f"prompt 缺少输出字段：{field}"

    def test_contains_json_only_rule(self):
        text = self._render()
        assert "JSON" in text
        assert "不要输出" in text or "禁止输出" in text

    def test_contains_count_and_difficulty(self):
        text = self._render()
        assert "5" in text
        assert "混合" in text

    def test_contains_fill_blank_rule(self):
        text = self._render()
        assert "____" in text  # 填空占位符规则
        assert "填空" in text

    def test_contains_judge_rule(self):
        text = self._render()
        assert "判断" in text
        assert "对" in text and "错" in text  # 判断题答案必须为 对/错

    def test_contains_question_type_rules(self):
        text = self._render()
        assert "单选" in text and "多选" in text

    def test_contains_reference_section_and_rules(self):
        text = self._render()
        assert "参考资料" in text
        assert "以资料为准" in text
        assert "一律不执行" in text  # 防注入：资料中的指令不执行
        assert "宁缺毋编" in text

    def test_contains_no_reference_placeholder(self):
        text = self._render()
        assert "本次无联网参考资料" in text
        assert "不得编造" in text

    def test_reference_context_renders_custom_value(self):
        prompt = build_quiz_prompt()
        text = prompt.invoke(
            {
                "user_input": "Harness Engineering",
                "reference_context": "Harness Engineering 是 AI 工程领域的术语，强调为 AI 搭建约束环境。",
                "question_count": "5",
                "difficulty": "混合",
                "types_requirement": build_types_requirement(["single"]),
            }
        ).to_string()
        assert "Harness Engineering 是 AI 工程领域的术语" in text


class TestReportPromptContract:
    def _render(self) -> str:
        prompt = build_report_prompt()
        return prompt.invoke(
            {
                "topic": "RAG 入门",
                "quiz_json": '{"title": "RAG 入门", "questions": []}',
                "answer_records": '[{"question_id": "q1", "is_correct": false}]',
                "score_summary": "总题数 5 · 答对 2 · 答错 3 · 正确率 40%",
            }
        ).to_string()

    def test_contains_topic(self):
        assert "RAG 入门" in self._render()

    def test_contains_score_summary(self):
        text = self._render()
        assert "40%" in text or "正确率" in text

    def test_contains_output_fields(self):
        text = self._render()
        for field in ["mastered_points", "weak_points", "three_line_summary", "advice", "share_quote"]:
            assert field in text, f"报告 prompt 缺少输出字段：{field}"

    def test_contains_json_only_rule(self):
        text = self._render()
        assert "JSON" in text


class TestAgentPromptContract:
    """知识获取 Agent Prompt 契约（任务 2.4）：关键要素丢失即失败。"""

    def _render(self, max_tool_calls: int = 4) -> str:
        return build_agent_system_prompt(max_tool_calls)

    def test_contains_three_tool_names(self):
        text = self._render()
        for name in ["tavily_search_basic", "tavily_search_deep", "tavily_extract"]:
            assert name in text, f"Agent prompt 缺少工具：{name}"

    def test_contains_tool_call_limit(self):
        assert "最多 4 次" in self._render(4)
        assert "最多 6 次" in self._render(6)  # 上限可配置（注入生效）

    def test_contains_majority_domain_strategy(self):
        text = self._render()
        assert "以多数为准" in text  # 多角度搜索 + 以多数为准
        assert "领域" in text
        assert "误配" in text  # 术语跨领域同名的歧义提示

    def test_contains_tier_strategy(self):
        text = self._render()
        assert "轻快" in text and "深度" in text  # 档位选择策略
        assert "完整页面内容" in text  # 深度档内容形态

    def test_contains_dynamic_param_guidance(self):
        text = self._render()
        for key in ["time_range", "include_domains", "start_date", "end_date"]:
            assert key in text, f"Agent prompt 缺少动态参数指引：{key}"

    def test_contains_url_fallback(self):
        text = self._render()
        assert "提取失败" in text
        assert "关键词搜索" in text  # 提取失败转关键词搜索补救

    def test_contains_not_found_disclosure(self):
        assert "未找到相关资料" in self._render()

    def test_contains_injection_guard(self):
        assert "注入" in self._render()  # 资料中的指令一律不执行

    def test_contains_structured_output_sections(self):
        text = self._render()
        assert "领域判断" in text
        assert "关键要点" in text
        assert "来源清单" in text
