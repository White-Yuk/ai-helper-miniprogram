"""可靠性评估器测试（任务 5.1）：mock 链（可靠 / 不可靠 / 重试 / 最终失败）。"""
from __future__ import annotations

import pytest

from app.llm import assessor
from app.models.quiz import ReliabilityAssessment
from tests.conftest import FakeChain


class TestAssessReliability:
    def test_reliable(self, monkeypatch):
        monkeypatch.setattr(
            assessor,
            "_build_assess_chain",
            lambda: FakeChain([ReliabilityAssessment(reliable=True, reason="通用知识")]),
        )
        result = assessor.assess_reliability("什么是 HTTP")
        assert result.reliable is True
        assert result.reason == "通用知识"

    def test_unreliable(self, monkeypatch):
        monkeypatch.setattr(
            assessor,
            "_build_assess_chain",
            lambda: FakeChain([ReliabilityAssessment(reliable=False, reason="可能是训练数据之后的新概念")]),
        )
        result = assessor.assess_reliability("Harness Engineering")
        assert result.reliable is False

    def test_retry_then_success(self, monkeypatch):
        chain = FakeChain([RuntimeError("boom"), ReliabilityAssessment(reliable=True, reason="ok")])
        monkeypatch.setattr(assessor, "_build_assess_chain", lambda: chain)

        result = assessor.assess_reliability("x")

        assert result.reliable is True
        assert chain.call_count == 2

    def test_invalid_structure_retried(self, monkeypatch):
        chain = FakeChain(["not-a-model", ReliabilityAssessment(reliable=False, reason="不确定")])
        monkeypatch.setattr(assessor, "_build_assess_chain", lambda: chain)

        result = assessor.assess_reliability("x")

        assert result.reliable is False
        assert chain.call_count == 2

    def test_final_failure_raises(self, monkeypatch):
        chain = FakeChain([RuntimeError("boom")])
        monkeypatch.setattr(assessor, "_build_assess_chain", lambda: chain)

        with pytest.raises(RuntimeError):
            assessor.assess_reliability("x")

        assert chain.call_count == 2  # 初次 + 1 次重试


class TestAssessorPromptContract:
    def _render(self) -> str:
        return (
            assessor.build_assessor_prompt()
            .invoke({"user_input": "Harness Engineering", "today": "2026-10-06"})
            .to_string()
        )

    def test_contains_current_date(self):
        assert "2026-10-06" in self._render()

    def test_contains_new_concept_hint(self):
        assert "训练数据" in self._render()  # 提示"可能是训练数据之后的新概念"

    def test_contains_conservative_rule(self):
        text = self._render()
        assert "不可靠" in text
        assert "宁可保守" in text  # 不确定时必须报不可靠

    def test_contains_self_contained_rule(self):
        assert "自包含" in self._render()  # 自包含解释性文本 → 可靠

    def test_contains_user_input(self):
        assert "Harness Engineering" in self._render()
