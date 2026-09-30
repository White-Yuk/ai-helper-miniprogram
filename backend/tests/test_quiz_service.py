"""出题服务测试：正常生成、结构校验、自动重试、重试耗尽兜底、LLM 异常兜底。"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.exceptions import BizException
from app.models.quiz import QuizData, QuizGenerateRequest
from app.services.quiz_service import (
    QuizValidationError,
    generate_quiz,
    validate_quiz_quality,
)
from tests.conftest import FakeChain, make_question


def make_request(**overrides) -> QuizGenerateRequest:
    defaults = dict(
        user_input="什么是 RAG？",
        question_count=4,
        question_types=["single", "multiple", "judge", "fill"],
    )
    defaults.update(overrides)
    return QuizGenerateRequest(**defaults)


class TestValidateQuizQuality:
    def test_valid_quiz_passes(self, sample_quiz_data: QuizData):
        validate_quiz_quality(sample_quiz_data, make_request())

    def test_wrong_question_count_rejected(self, sample_quiz_data: QuizData):
        with pytest.raises(QuizValidationError):
            validate_quiz_quality(sample_quiz_data, make_request(question_count=5))

    def test_missing_requested_type_rejected(self):
        data = QuizData(
            title="x",
            summary="x",
            questions=[make_question("q1", "single"), make_question("q2", "single"), make_question("q3", "single")],
        )
        # 请求了 single + fill（共 3 题），但数据里没有 fill
        with pytest.raises(QuizValidationError):
            validate_quiz_quality(data, make_request(question_count=3, question_types=["single", "fill"]))

    def test_unrequested_type_rejected(self):
        data = QuizData(
            title="x",
            summary="x",
            questions=[make_question("q1", "single"), make_question("q2", "single"), make_question("q3", "judge")],
        )
        # 请求只有 single，但数据里出现了 judge
        with pytest.raises(QuizValidationError):
            validate_quiz_quality(data, make_request(question_count=3, question_types=["single"]))

    def test_single_choice_bad_answer_key_rejected(self):
        data = QuizData(
            title="x",
            summary="x",
            questions=[
                make_question("q1", "single", answer=["D"]),
                make_question("q2", "single"),
                make_question("q3", "single"),
            ],
        )
        with pytest.raises(QuizValidationError):
            validate_quiz_quality(data, make_request(question_count=3, question_types=["single"]))

    def test_single_choice_multi_answers_rejected(self):
        data = QuizData(
            title="x",
            summary="x",
            questions=[
                make_question("q1", "single", answer=["A", "B"]),
                make_question("q2", "single"),
                make_question("q3", "single"),
            ],
        )
        with pytest.raises(QuizValidationError):
            validate_quiz_quality(data, make_request(question_count=3, question_types=["single"]))

    def test_multiple_choice_single_answer_rejected(self):
        data = QuizData(
            title="x",
            summary="x",
            questions=[
                make_question("q1", "multiple", answer=["A"]),
                make_question("q2", "multiple"),
                make_question("q3", "multiple"),
            ],
        )
        with pytest.raises(QuizValidationError):
            validate_quiz_quality(data, make_request(question_count=3, question_types=["multiple"]))

    def test_fill_blank_marker_mismatch_rejected(self):
        data = QuizData(
            title="x",
            summary="x",
            questions=[
                make_question("q1", "fill", stem="没有下划线的题干", answer=["检索"]),
                make_question("q2", "fill"),
                make_question("q3", "fill"),
            ],
        )
        with pytest.raises(QuizValidationError):
            validate_quiz_quality(data, make_request(question_count=3, question_types=["fill"]))

    def test_duplicate_question_ids_rejected(self):
        data = QuizData(
            title="x",
            summary="x",
            questions=[
                make_question("q1", "single"),
                make_question("q1", "single"),
                make_question("q2", "single"),
            ],
        )
        with pytest.raises(QuizValidationError):
            validate_quiz_quality(data, make_request(question_count=3, question_types=["single"]))


class TestGenerateQuiz:
    def test_success_first_try(self, sample_quiz_data: QuizData):
        chain = FakeChain([sample_quiz_data])
        result = generate_quiz(make_request(), chain)

        assert result.quiz_id.startswith("quiz_")
        assert result.title == "RAG 入门"
        assert len(result.questions) == 4
        assert chain.call_count == 1

    def test_retry_on_invalid_structure_then_success(self, sample_quiz_data: QuizData):
        bad = QuizData(title="x", summary="x", questions=[make_question("q1", "single")])  # 数量不符
        chain = FakeChain([bad, sample_quiz_data])

        result = generate_quiz(make_request(), chain)
        assert len(result.questions) == 4
        assert chain.call_count == 2  # 第一次失败后自动重试

    def test_retry_on_exception_then_success(self, sample_quiz_data: QuizData):
        chain = FakeChain([RuntimeError("mock timeout"), sample_quiz_data])
        result = generate_quiz(make_request(), chain)
        assert len(result.questions) == 4
        assert chain.call_count == 2

    def test_fail_after_retries_exhausted(self):
        bad = QuizData(title="x", summary="x", questions=[make_question("q1", "single")])
        chain = FakeChain([bad])
        settings = get_settings()

        with pytest.raises(BizException) as exc_info:
            generate_quiz(make_request(), chain)

        assert exc_info.value.code == 4001
        assert chain.call_count == settings.llm_max_retries + 1  # 首次 + 重试次数

    def test_fail_on_persistent_llm_exception(self):
        chain = FakeChain([RuntimeError("mock 500")])
        settings = get_settings()

        with pytest.raises(BizException) as exc_info:
            generate_quiz(make_request(), chain)

        assert exc_info.value.code == 4001
        assert chain.call_count == settings.llm_max_retries + 1
