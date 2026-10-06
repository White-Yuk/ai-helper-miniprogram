"""出题服务测试：正常生成、结构校验、自动重试、重试耗尽兜底、LLM 异常兜底。"""
from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.exceptions import BizException
from app.models.quiz import AgentTrace, QuizData, QuizGenerateRequest, QuizSource, ReliabilityAssessment
from app.prompts.quiz_prompt import NO_REFERENCE_CONTEXT
from app.services import quiz_service
from app.services.knowledge_agent import KnowledgeResult
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


# ---- 带知识获取的编排（任务 6.1）：Agent / 评估器 / 步骤回调注入 ----


def make_knowledge(**overrides) -> KnowledgeResult:
    defaults = dict(
        summary="资料摘要：RAG（检索增强生成）通过检索外部知识补充大模型回答。",
        sources=[{"title": "RAG 导论", "url": "https://a.example/rag"}],
        trace={"search_count": 1, "extract_count": 0, "queries": ["RAG 是什么"], "doc_count": 3},
        has_valid_content=True,
    )
    defaults.update(overrides)
    return KnowledgeResult(**defaults)


def make_empty_knowledge(**overrides) -> KnowledgeResult:
    defaults = dict(
        summary="",
        sources=[],
        trace={"search_count": 0, "extract_count": 0, "queries": [], "doc_count": 0},
        has_valid_content=False,
    )
    defaults.update(overrides)
    return KnowledgeResult(**defaults)


class TestGenerateQuizWithGrounding:
    """行为矩阵（design D7）：未配置 / 有内容 / 无内容（可靠 / 不可靠）/ 降级 / URL。"""

    def _enable(self, monkeypatch, knowledge: KnowledgeResult) -> None:
        monkeypatch.setattr(quiz_service, "is_enabled", lambda: True)
        monkeypatch.setattr(quiz_service, "acquire_knowledge", lambda text, on_step=None: knowledge)

    def test_disabled_passthrough_without_agent(self, sample_quiz_data, monkeypatch):
        monkeypatch.setattr(quiz_service, "is_enabled", lambda: False)
        called: list = []
        monkeypatch.setattr(
            quiz_service, "acquire_knowledge", lambda *a, **k: called.append(1) or make_empty_knowledge()
        )
        monkeypatch.setattr(
            quiz_service, "assess_reliability", lambda _t: (_ for _ in ()).throw(AssertionError("未配置不应评估"))
        )
        chain = FakeChain([sample_quiz_data])
        steps: list = []

        data = quiz_service.generate_quiz_with_grounding(make_request(), chain, on_step=lambda *a: steps.append(a))

        assert data.sources is None
        assert data.agent_trace is None
        assert called == []
        assert [s[0] for s in steps] == ["stage:generate", "stage:generate", "stage:finish"]
        assert chain.calls[0]["reference_context"] == NO_REFERENCE_CONTEXT

    def test_valid_content_injects_and_attaches(self, sample_quiz_data, monkeypatch):
        knowledge = make_knowledge()
        captured: dict = {}

        def fake_acquire(text, on_step=None):
            captured["text"] = text
            captured["on_step"] = on_step
            return knowledge

        monkeypatch.setattr(quiz_service, "is_enabled", lambda: True)
        monkeypatch.setattr(quiz_service, "acquire_knowledge", fake_acquire)
        monkeypatch.setattr(
            quiz_service, "assess_reliability", lambda _t: (_ for _ in ()).throw(AssertionError("有资料不应评估"))
        )
        chain = FakeChain([sample_quiz_data])
        steps: list = []

        data = quiz_service.generate_quiz_with_grounding(make_request(), chain, on_step=lambda *a: steps.append(a))

        assert data.sources == [QuizSource(title="RAG 导论", url="https://a.example/rag")]
        assert data.agent_trace == AgentTrace(search_count=1, extract_count=0, queries=["RAG 是什么"], doc_count=3)
        assert chain.calls[0]["reference_context"] == knowledge.summary
        assert captured["text"] == "什么是 RAG？"
        assert callable(captured["on_step"])  # 步骤回穿透传给 Agent（工具级步骤）
        assert [s[0] for s in steps] == ["stage:judge", "stage:generate", "stage:generate", "stage:finish"]

    def test_no_content_reliable_generates_pure(self, sample_quiz_data, monkeypatch):
        self._enable(monkeypatch, make_empty_knowledge())
        monkeypatch.setattr(
            quiz_service, "assess_reliability", lambda _t: ReliabilityAssessment(reliable=True, reason="常见知识")
        )
        chain = FakeChain([sample_quiz_data])

        data = quiz_service.generate_quiz_with_grounding(make_request(), chain)

        assert data.sources == []
        assert data.agent_trace is None
        assert chain.calls[0]["reference_context"] == NO_REFERENCE_CONTEXT

    def test_no_content_unreliable_raises_4006(self, monkeypatch):
        self._enable(monkeypatch, make_empty_knowledge())
        monkeypatch.setattr(
            quiz_service, "assess_reliability", lambda _t: ReliabilityAssessment(reliable=False, reason="可能是新概念")
        )
        chain = FakeChain([QuizData(title="x", summary="x", questions=[make_question("q1", "single")])])

        with pytest.raises(BizException) as err:
            quiz_service.generate_quiz_with_grounding(make_request(), chain)

        assert err.value.code == 4006
        assert chain.call_count == 0  # 不出题

    def test_assessor_failure_degrades_to_pure_generation(self, sample_quiz_data, monkeypatch):
        self._enable(monkeypatch, make_empty_knowledge())

        def _raise(_t):
            raise RuntimeError("assessor down")

        monkeypatch.setattr(quiz_service, "assess_reliability", _raise)
        chain = FakeChain([sample_quiz_data])

        data = quiz_service.generate_quiz_with_grounding(make_request(), chain)

        assert chain.call_count == 1
        assert data.sources == []

    def test_agent_timeout_degrades_into_assess_flow(self, sample_quiz_data, monkeypatch):
        # Agent 超时 → 空结果（同“无有效内容”分支）→ 评估可靠 → 正常出题
        self._enable(monkeypatch, make_empty_knowledge())
        monkeypatch.setattr(
            quiz_service, "assess_reliability", lambda _t: ReliabilityAssessment(reliable=True, reason="ok")
        )
        chain = FakeChain([sample_quiz_data])

        data = quiz_service.generate_quiz_with_grounding(make_request(), chain)

        assert data.title == sample_quiz_data.title

    def test_url_success_attaches_extract_trace(self, sample_quiz_data, monkeypatch):
        knowledge = make_knowledge(
            sources=[{"title": "文章", "url": "https://page.example/post"}],
            trace={"search_count": 0, "extract_count": 1, "queries": [], "doc_count": 1},
        )
        self._enable(monkeypatch, knowledge)
        chain = FakeChain([sample_quiz_data])

        data = quiz_service.generate_quiz_with_grounding(make_request(user_input="https://page.example/post"), chain)

        assert data.agent_trace.extract_count == 1
        assert data.sources[0].url == "https://page.example/post"

    def test_no_content_with_activity_keeps_trace(self, sample_quiz_data, monkeypatch):
        # 无资料但有检索活动（如检索 0 条）→ 保留轨迹供溯源；来源为空列表
        knowledge = make_empty_knowledge(
            trace={"search_count": 3, "extract_count": 1, "queries": ["a", "b", "c"], "doc_count": 0}
        )
        self._enable(monkeypatch, knowledge)
        monkeypatch.setattr(
            quiz_service, "assess_reliability", lambda _t: ReliabilityAssessment(reliable=True, reason="ok")
        )
        chain = FakeChain([sample_quiz_data])

        data = quiz_service.generate_quiz_with_grounding(make_request(), chain)

        assert data.sources == []
        assert data.agent_trace == AgentTrace(search_count=3, extract_count=1, queries=["a", "b", "c"], doc_count=0)
