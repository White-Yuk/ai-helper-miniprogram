"""GET /me 续答摘要测试（阶段 3 接入真实数据，TDD 先行）。"""
from __future__ import annotations

import pytest

from app.api.v1.routes.quiz import get_quiz_chain
from tests.conftest import FakeChain, login_headers

pytestmark = pytest.mark.usefixtures("auth_settings")


VALID_PAYLOAD = {
    "user_input": "什么是 RAG？",
    "question_count": 4,
    "difficulty": "mixed",
    "question_types": ["single", "multiple", "judge", "fill"],
}


def _record(qid: str, correct: bool = True) -> dict:
    return {"question_id": qid, "selected_answers": ["A"], "is_correct": correct, "duration_ms": 1000}


class TestMeContinueLearning:
    def test_continue_learning_after_partial_progress(self, app, client_db, sample_quiz_data):
        headers = login_headers(client_db, "device_me")
        app.dependency_overrides[get_quiz_chain] = lambda: FakeChain([sample_quiz_data])

        resp = client_db.post("/api/v1/quiz/generate", json=VALID_PAYLOAD, headers=headers)
        quiz_id = resp.json()["data"]["quiz_id"]
        client_db.put(
            f"/api/v1/quiz/{quiz_id}/progress",
            json={"current_index": 2, "records": [_record("q1"), _record("q2")]},
            headers=headers,
        )

        resp = client_db.get("/api/v1/me", headers=headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["continue_learning"] == {
            "quiz_id": quiz_id,
            "title": "RAG 入门",
            "current_index": 2,
            "total": 4,
        }

    def test_continue_learning_null_without_doing(self, client_db):
        headers = login_headers(client_db, "device_me_empty")

        resp = client_db.get("/api/v1/me", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["continue_learning"] is None

    def test_continue_learning_null_after_done(self, app, client_db, sample_quiz_data):
        headers = login_headers(client_db, "device_me_done")
        app.dependency_overrides[get_quiz_chain] = lambda: FakeChain([sample_quiz_data])

        resp = client_db.post("/api/v1/quiz/generate", json=VALID_PAYLOAD, headers=headers)
        quiz_id = resp.json()["data"]["quiz_id"]
        client_db.post(
            f"/api/v1/quiz/{quiz_id}/submit",
            json={"records": [_record(f"q{i}") for i in range(1, 5)]},
            headers=headers,
        )

        resp = client_db.get("/api/v1/me", headers=headers)

        assert resp.json()["data"]["continue_learning"] is None


class TestMeStats:
    """个人中心统计三宫格：真实数据（闯关数 / 累计答题 / 平均正确率）。"""

    def test_stats_zero_for_new_user(self, client_db):
        headers = login_headers(client_db, "device_stats_empty")

        resp = client_db.get("/api/v1/me", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["stats"] == {
            "quiz_count": 0,
            "answered_count": 0,
            "avg_accuracy": 0,
        }

    def test_stats_real_numbers_after_answers(self, app, client_db, sample_quiz_data):
        headers = login_headers(client_db, "device_stats_real")
        app.dependency_overrides[get_quiz_chain] = lambda: FakeChain([sample_quiz_data])

        resp = client_db.post("/api/v1/quiz/generate", json=VALID_PAYLOAD, headers=headers)
        quiz_id = resp.json()["data"]["quiz_id"]
        # 3 条作答：2 对 1 错 → 平均正确率 67%
        client_db.put(
            f"/api/v1/quiz/{quiz_id}/progress",
            json={
                "current_index": 3,
                "records": [_record("q1"), _record("q2"), _record("q3", correct=False)],
            },
            headers=headers,
        )

        resp = client_db.get("/api/v1/me", headers=headers)

        stats = resp.json()["data"]["stats"]
        assert stats["quiz_count"] == 1
        assert stats["answered_count"] == 3
        assert stats["avg_accuracy"] == 67
