"""出题接口测试：成功路径、参数校验（422 统一封装）、LLM 失败兜底。"""
from __future__ import annotations

from app.api.v1.routes.quiz import get_quiz_chain
from tests.conftest import FakeChain

VALID_PAYLOAD = {
    "user_input": "什么是 RAG？",
    "question_count": 4,
    "difficulty": "mixed",
    "question_types": ["single", "multiple", "judge", "fill"],
}


def override_quiz_chain(app, chain) -> None:
    app.dependency_overrides[get_quiz_chain] = lambda: chain


class TestQuizGenerateApi:
    def test_success(self, app, client, sample_quiz_data):
        override_quiz_chain(app, FakeChain([sample_quiz_data]))

        resp = client.post("/api/v1/quiz/generate", json=VALID_PAYLOAD)

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["message"] == "ok"
        data = body["data"]
        assert data["quiz_id"].startswith("quiz_")
        assert data["title"] == "RAG 入门"
        assert len(data["questions"]) == 4
        assert data["questions"][0]["type"] == "single"

    def test_request_validation_error_is_wrapped(self, client):
        resp = client.post("/api/v1/quiz/generate", json={**VALID_PAYLOAD, "user_input": "   "})

        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == 4000
        assert body["data"] is None
        assert "参数" in body["message"] or "校验" in body["message"]

    def test_invalid_question_count_rejected(self, client):
        resp = client.post("/api/v1/quiz/generate", json={**VALID_PAYLOAD, "question_count": 99})
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000

    def test_llm_failure_returns_biz_error(self, app, client):
        override_quiz_chain(app, FakeChain([RuntimeError("mock service down")]))

        resp = client.post("/api/v1/quiz/generate", json=VALID_PAYLOAD)

        assert resp.status_code == 502
        body = resp.json()
        assert body["code"] == 4001
        assert body["data"] is None
        assert "失败" in body["message"]
