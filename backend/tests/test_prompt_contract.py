"""Prompt 契约测试：确保提示词包含业务必需的全部要素。

作用：以后调整提示词时，任何关键要素（JSON 字段、填空题规则、判断题规则等）的丢失都会让测试失败。
"""
from __future__ import annotations

from app.prompts.quiz_prompt import build_quiz_prompt, build_types_requirement
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
