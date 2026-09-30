"""报告服务测试：后端统计正确率 + LLM 生成文字总结 + 失败重试与兜底。"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.exceptions import BizException
from app.models.report import AnswerRecord, ReportGenerateRequest, ReportLlmOutput
from app.models.quiz import QuizData
from app.services.report_service import generate_report
from tests.conftest import FakeChain


def make_records(flags: list[bool]) -> list[AnswerRecord]:
    return [
        AnswerRecord(question_id=f"q{i + 1}", selected_answers=["A"], is_correct=flag, duration_ms=900)
        for i, flag in enumerate(flags)
    ]


def make_request(quiz: QuizData, flags: list[bool]) -> ReportGenerateRequest:
    return ReportGenerateRequest(
        quiz_id="quiz_test",
        topic=quiz.title,
        questions=quiz.questions,
        answer_records=make_records(flags),
    )


def make_llm_output() -> ReportLlmOutput:
    return ReportLlmOutput(
        mastered_points=["核心概念"],
        weak_points=["应用场景"],
        three_line_summary=["要点一", "要点二", "要点三"],
        advice=["再练一关"],
        share_quote="把知识做成关卡，记忆会更深。",
    )


class TestGenerateReport:
    def test_success_accuracy_computed_by_backend(self, sample_quiz_data: QuizData):
        chain = FakeChain([make_llm_output()])
        request = make_request(sample_quiz_data, [True, False, True, False])  # 2/4 = 50%

        report = generate_report(request, chain)

        assert report.accuracy == 50  # 正确率由后端计算，不依赖 LLM
        assert report.mastered_points == ["核心概念"]
        assert report.weak_points == ["应用场景"]
        assert report.share_quote == "把知识做成关卡，记忆会更深。"
        assert chain.call_count == 1

        # 调用链输入应携带主题与统计数据
        inputs = chain.calls[0]
        assert inputs["topic"] == sample_quiz_data.title
        assert "50" in inputs["score_summary"]

    def test_all_correct(self, sample_quiz_data: QuizData):
        chain = FakeChain([make_llm_output()])
        report = generate_report(make_request(sample_quiz_data, [True, True, True, True]), chain)
        assert report.accuracy == 100

    def test_retry_on_exception_then_success(self, sample_quiz_data: QuizData):
        chain = FakeChain([RuntimeError("mock timeout"), make_llm_output()])
        report = generate_report(make_request(sample_quiz_data, [True, False, False, False]), chain)

        assert report.accuracy == 25
        assert chain.call_count == 2

    def test_fail_after_retries_exhausted(self, sample_quiz_data: QuizData):
        chain = FakeChain([RuntimeError("mock 500")])
        settings = get_settings()

        with pytest.raises(BizException) as exc_info:
            generate_report(make_request(sample_quiz_data, [True, False, False, False]), chain)

        assert exc_info.value.code == 4002
        assert chain.call_count == settings.llm_max_retries + 1
