"""数据模型（Pydantic）校验测试：请求参数约束与题目结构约束。"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.quiz import Option, Question, QuizGenerateRequest
from tests.conftest import make_question


class TestQuizGenerateRequest:
    def test_defaults(self):
        req = QuizGenerateRequest(user_input="什么是 RAG？")
        assert req.question_count == 5
        assert req.difficulty == "mixed"
        assert req.question_types == ["single", "multiple", "judge"]

    def test_strips_whitespace_input(self):
        req = QuizGenerateRequest(user_input="  什么是 RAG？  ")
        assert req.user_input == "什么是 RAG？"

    def test_rejects_blank_input(self):
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="   ")

    def test_rejects_too_long_input(self):
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="啊" * 2001)

    @pytest.mark.parametrize("count", [2, 11, 0, -1])
    def test_rejects_bad_question_count(self, count: int):
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="RAG", question_count=count)

    @pytest.mark.parametrize("count", [3, 5, 10])
    def test_accepts_valid_question_count(self, count: int):
        req = QuizGenerateRequest(user_input="RAG", question_count=count)
        assert req.question_count == count

    def test_rejects_unknown_difficulty(self):
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="RAG", difficulty="nightmare")

    def test_rejects_empty_question_types(self):
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="RAG", question_types=[])

    def test_rejects_unknown_question_type(self):
        with pytest.raises(ValidationError):
            QuizGenerateRequest(user_input="RAG", question_types=["single", "essay"])

    def test_deduplicates_question_types(self):
        req = QuizGenerateRequest(user_input="RAG", question_types=["single", "single", "judge"])
        assert req.question_types == ["single", "judge"]


class TestQuestionModel:
    def test_single_choice_valid(self):
        q = make_question("q1", "single")
        assert q.type == "single"
        assert len(q.options) == 2
        assert q.answer == ["A"]

    def test_judge_answer_must_be_dui_or_cuo(self):
        with pytest.raises(ValidationError):
            make_question("q3", "judge", answer=["maybe"])

    def test_fill_has_no_options(self):
        q = make_question("q4", "fill")
        assert q.options == []

    def test_answer_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            make_question("q1", "single", answer=[])

    def test_rejects_unknown_type(self):
        with pytest.raises(ValidationError):
            Question(id="q9", type="essay", stem="x", options=[], answer=["a"], explanation="x", knowledge_point="x", difficulty="easy")

    def test_option_key_normalized_upper(self):
        opt = Option(key="a", text="选项")
        assert opt.key == "A"
