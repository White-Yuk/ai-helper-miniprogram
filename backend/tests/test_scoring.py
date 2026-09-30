"""统计逻辑测试：正确率与得分摘要计算。"""
from __future__ import annotations

from app.models.report import AnswerRecord
from app.services.scoring_service import compute_accuracy, compute_score_summary


def rec(idx: int, correct: bool, duration_ms: int = 1000) -> AnswerRecord:
    return AnswerRecord(
        question_id=f"q{idx}",
        selected_answers=["A"],
        is_correct=correct,
        duration_ms=duration_ms,
    )


class TestComputeAccuracy:
    def test_all_correct(self):
        assert compute_accuracy([rec(i, True) for i in range(5)]) == 100

    def test_all_wrong(self):
        assert compute_accuracy([rec(i, False) for i in range(4)]) == 0

    def test_partial(self):
        records = [rec(1, True), rec(2, False), rec(3, True), rec(4, False), rec(5, False)]
        assert compute_accuracy(records) == 40

    def test_rounding(self):
        # 2/3 = 66.67% -> 67
        records = [rec(1, True), rec(2, True), rec(3, False)]
        assert compute_accuracy(records) == 67

    def test_empty_returns_zero(self):
        assert compute_accuracy([]) == 0


class TestComputeScoreSummary:
    def test_counts(self):
        records = [rec(1, True), rec(2, True), rec(3, False)]
        summary = compute_score_summary(records)
        assert summary["total"] == 3
        assert summary["correct"] == 2
        assert summary["wrong"] == 1
        assert summary["accuracy"] == 67

    def test_empty(self):
        summary = compute_score_summary([])
        assert summary["total"] == 0
        assert summary["correct"] == 0
        assert summary["wrong"] == 0
        assert summary["accuracy"] == 0
