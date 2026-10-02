"""阶段 3：历史答题记录 + 续答 接口测试（TDD 先行）。

覆盖：
- 生成题库（可选登录）：带 token 落库 / 匿名不落库 / 无效 token 拒绝
- PUT /quiz/{id}/progress：保存、幂等覆盖、脏数据容错、越权与未登录
- POST /quiz/{id}/submit：完成状态、幂等
- GET /quiz/unfinished：完整数据、空态、过滤已完成、取最近更新
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.v1.routes.quiz import get_quiz_chain
from app.models.records import Answer, Quiz
from tests.conftest import FakeChain, login_headers

pytestmark = pytest.mark.usefixtures("auth_settings")


VALID_PAYLOAD = {
    "user_input": "什么是 RAG？",
    "question_count": 4,
    "difficulty": "mixed",
    "question_types": ["single", "multiple", "judge", "fill"],
}


def override_quiz_chain(app, chain) -> None:
    app.dependency_overrides[get_quiz_chain] = lambda: chain


def record(qid: str, correct: bool = True, selected: list[str] | None = None) -> dict:
    return {
        "question_id": qid,
        "selected_answers": selected if selected is not None else ["A"],
        "is_correct": correct,
        "duration_ms": 1500,
    }


@pytest.fixture()
def generated(client_db, app, sample_quiz_data):
    """登录 + 生成一份已落库的题库，返回 (headers, quiz_id)。"""
    headers = login_headers(client_db, "device_stage3")
    override_quiz_chain(app, FakeChain([sample_quiz_data]))
    resp = client_db.post("/api/v1/quiz/generate", json=VALID_PAYLOAD, headers=headers)
    assert resp.status_code == 200, resp.text
    return headers, resp.json()["data"]["quiz_id"]


class TestGeneratePersist:
    """生成题库：可选登录的落库行为。"""

    def test_generate_with_token_persists_quiz(self, app, client_db, db_session, sample_quiz_data):
        headers, quiz_id = self._generate(client_db, app, sample_quiz_data, login_headers(client_db, "device_a"))

        quiz = db_session.scalars(select(Quiz)).one()
        assert quiz.quiz_id == quiz_id
        assert quiz.status == "doing"
        assert quiz.current_index == 0
        assert quiz.completed_at is None
        assert quiz.title == sample_quiz_data.title
        assert len(quiz.questions) == 4
        assert quiz.questions[0]["id"] == "q1"

    def test_generate_anonymous_not_persisted(self, app, client_db, db_session, sample_quiz_data):
        override_quiz_chain(app, FakeChain([sample_quiz_data]))

        resp = client_db.post("/api/v1/quiz/generate", json=VALID_PAYLOAD)

        assert resp.status_code == 200
        assert resp.json()["data"]["quiz_id"].startswith("quiz_")
        assert db_session.scalars(select(Quiz)).all() == []

    def test_generate_invalid_token_rejected(self, app, client_db, db_session, sample_quiz_data):
        override_quiz_chain(app, FakeChain([sample_quiz_data]))

        resp = client_db.post(
            "/api/v1/quiz/generate",
            json=VALID_PAYLOAD,
            headers={"Authorization": "Bearer not-a-token"},
        )

        assert resp.status_code == 401
        assert resp.json()["code"] == 4003
        assert db_session.scalars(select(Quiz)).all() == []

    @staticmethod
    def _generate(client, app, sample_quiz_data, headers):
        override_quiz_chain(app, FakeChain([sample_quiz_data]))
        resp = client.post("/api/v1/quiz/generate", json=VALID_PAYLOAD, headers=headers)
        assert resp.status_code == 200, resp.text
        return headers, resp.json()["data"]["quiz_id"]


class TestSaveProgress:
    """PUT /quiz/{quiz_id}/progress：幂等保存中途进度。"""

    def test_save_progress_success(self, client_db, db_session, generated):
        headers, quiz_id = generated

        resp = client_db.put(
            f"/api/v1/quiz/{quiz_id}/progress",
            json={"current_index": 2, "records": [record("q1"), record("q2", correct=False)]},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["current_index"] == 2
        assert data["saved_count"] == 2

        quiz = db_session.scalars(select(Quiz)).one()
        assert quiz.current_index == 2
        assert quiz.status == "doing"

        answers = db_session.scalars(select(Answer).order_by(Answer.id)).all()
        assert [a.question_id for a in answers] == ["q1", "q2"]
        assert answers[0].question_type == "single"
        assert answers[0].knowledge_point == "核心概念"
        assert answers[1].is_correct is False
        assert answers[1].duration_ms == 1500

    def test_save_progress_is_idempotent(self, client_db, db_session, generated):
        headers, quiz_id = generated
        url = f"/api/v1/quiz/{quiz_id}/progress"

        client_db.put(url, json={"current_index": 2, "records": [record("q1"), record("q2")]}, headers=headers)
        resp = client_db.put(url, json={"current_index": 1, "records": [record("q1")]}, headers=headers)

        assert resp.status_code == 200
        answers = db_session.scalars(select(Answer)).all()
        assert len(answers) == 1
        assert db_session.scalars(select(Quiz)).one().current_index == 1

    def test_save_progress_skips_unknown_question_id(self, client_db, db_session, generated):
        headers, quiz_id = generated

        resp = client_db.put(
            f"/api/v1/quiz/{quiz_id}/progress",
            json={"current_index": 1, "records": [record("q1"), record("ghost")]},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["saved_count"] == 1
        answers = db_session.scalars(select(Answer)).all()
        assert [a.question_id for a in answers] == ["q1"]

    def test_save_progress_dedupes_question_ids(self, client_db, db_session, generated):
        headers, quiz_id = generated

        resp = client_db.put(
            f"/api/v1/quiz/{quiz_id}/progress",
            json={
                "current_index": 1,
                "records": [record("q1", correct=False), record("q1", correct=True, selected=["B"])],
            },
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["saved_count"] == 1
        answers = db_session.scalars(select(Answer)).all()
        assert len(answers) == 1
        assert answers[0].is_correct is True
        assert answers[0].selected_answers == ["B"]

    def test_save_progress_clamps_current_index(self, client_db, db_session, generated):
        headers, quiz_id = generated

        resp = client_db.put(
            f"/api/v1/quiz/{quiz_id}/progress",
            json={"current_index": 99, "records": [record("q1")]},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["data"]["current_index"] == 4  # 总题数 4

    def test_save_progress_requires_login(self, client_db, generated):
        _, quiz_id = generated

        resp = client_db.put(
            f"/api/v1/quiz/{quiz_id}/progress",
            json={"current_index": 1, "records": [record("q1")]},
        )

        assert resp.status_code == 401
        assert resp.json()["code"] == 4003

    def test_save_progress_quiz_not_found(self, client_db, generated):
        headers, _ = generated

        resp = client_db.put(
            "/api/v1/quiz/quiz_not_exists/progress",
            json={"current_index": 1, "records": [record("q1")]},
            headers=headers,
        )

        assert resp.status_code == 404
        assert resp.json()["code"] == 4005

    def test_save_progress_other_users_quiz_rejected(self, client_db, db_session, generated):
        _, quiz_id = generated
        other_headers = login_headers(client_db, "device_other")

        resp = client_db.put(
            f"/api/v1/quiz/{quiz_id}/progress",
            json={"current_index": 1, "records": [record("q1")]},
            headers=other_headers,
        )

        assert resp.status_code == 404
        assert resp.json()["code"] == 4005
        assert db_session.scalars(select(Answer)).all() == []


class TestSubmitQuiz:
    """POST /quiz/{quiz_id}/submit：提交完整作答，quiz 置 done。"""

    def test_submit_success(self, client_db, db_session, generated):
        headers, quiz_id = generated
        records = [record(f"q{i}") for i in range(1, 5)]

        resp = client_db.post(
            f"/api/v1/quiz/{quiz_id}/submit",
            json={"records": records},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["status"] == "done"
        assert data["answered_count"] == 4

        quiz = db_session.scalars(select(Quiz)).one()
        assert quiz.status == "done"
        assert quiz.completed_at is not None
        assert quiz.current_index == 4
        assert len(db_session.scalars(select(Answer)).all()) == 4

    def test_submit_is_idempotent(self, client_db, db_session, generated):
        headers, quiz_id = generated
        records = [record(f"q{i}") for i in range(1, 5)]
        url = f"/api/v1/quiz/{quiz_id}/submit"

        client_db.post(url, json={"records": records}, headers=headers)
        resp = client_db.post(url, json={"records": records}, headers=headers)

        assert resp.status_code == 200
        assert len(db_session.scalars(select(Answer)).all()) == 4

    def test_submit_requires_login(self, client_db, generated):
        _, quiz_id = generated

        resp = client_db.post(f"/api/v1/quiz/{quiz_id}/submit", json={"records": [record("q1")]})

        assert resp.status_code == 401
        assert resp.json()["code"] == 4003

    def test_submit_other_users_quiz_rejected(self, client_db, generated):
        _, quiz_id = generated
        other_headers = login_headers(client_db, "device_other")

        resp = client_db.post(
            f"/api/v1/quiz/{quiz_id}/submit",
            json={"records": [record("q1")]},
            headers=other_headers,
        )

        assert resp.status_code == 404
        assert resp.json()["code"] == 4005


class TestUnfinishedQuiz:
    """GET /quiz/unfinished：最近未完成闯关（供“上次没打完的”卡片与续答恢复）。"""

    def test_returns_latest_doing_full_payload(self, client_db, generated):
        headers, quiz_id = generated
        client_db.put(
            f"/api/v1/quiz/{quiz_id}/progress",
            json={"current_index": 2, "records": [record("q1"), record("q2", correct=False)]},
            headers=headers,
        )

        resp = client_db.get("/api/v1/quiz/unfinished", headers=headers)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["quiz_id"] == quiz_id
        assert data["title"] == "RAG 入门"
        assert data["total"] == 4
        assert data["current_index"] == 2
        assert len(data["questions"]) == 4
        assert [r["question_id"] for r in data["records"]] == ["q1", "q2"]
        assert data["records"][1]["is_correct"] is False
        assert data["updated_at"]

    def test_returns_null_when_none(self, client_db):
        headers = login_headers(client_db, "device_empty")

        resp = client_db.get("/api/v1/quiz/unfinished", headers=headers)

        assert resp.status_code == 200
        assert resp.json() == {"code": 0, "message": "ok", "data": None}

    def test_ignores_done_quiz(self, client_db, generated):
        headers, quiz_id = generated
        client_db.post(
            f"/api/v1/quiz/{quiz_id}/submit",
            json={"records": [record(f"q{i}") for i in range(1, 5)]},
            headers=headers,
        )

        resp = client_db.get("/api/v1/quiz/unfinished", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["data"] is None

    def test_returns_most_recently_updated(self, app, client_db, sample_quiz_data, generated):
        headers, first_quiz_id = generated

        override_quiz_chain(app, FakeChain([sample_quiz_data]))
        resp = client_db.post("/api/v1/quiz/generate", json=VALID_PAYLOAD, headers=headers)
        second_quiz_id = resp.json()["data"]["quiz_id"]

        # 对更早生成的 quiz 保存进度 -> 它成为“最近更新”的未完成闯关
        client_db.put(
            f"/api/v1/quiz/{first_quiz_id}/progress",
            json={"current_index": 1, "records": [record("q1")]},
            headers=headers,
        )

        resp = client_db.get("/api/v1/quiz/unfinished", headers=headers)

        assert resp.json()["data"]["quiz_id"] == first_quiz_id
        assert second_quiz_id != first_quiz_id

    def test_requires_login(self, client_db):
        resp = client_db.get("/api/v1/quiz/unfinished")
        assert resp.status_code == 401
        assert resp.json()["code"] == 4003
