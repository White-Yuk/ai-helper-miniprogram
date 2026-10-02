"""阶段 6：错题本接口测试（GET /wrongbook、POST /wrongbook/redo，TDD 先行）。

覆盖：
- 列表：只含答错且未订正的题；已重做答对 -> 移除；错误次数与上次错误答案
- 重做提交：追加记录、返回剩余数、答错保留
- 归属 / 参数校验、未登录
"""
from __future__ import annotations

import pytest

from tests.conftest import login_user, make_answer_record, make_quiz_record

pytestmark = pytest.mark.usefixtures("auth_settings")


def submit_redo(client, headers, quiz_id: str, question_id: str, *, correct: bool, selected: list[str] | None = None):
    return client.post(
        "/api/v1/wrongbook/redo",
        json={
            "quiz_id": quiz_id,
            "question_id": question_id,
            "selected_answers": selected or (["A"] if correct else ["Z"]),
            "is_correct": correct,
            "duration_ms": 3000,
        },
        headers=headers,
    )


class TestWrongbookList:
    def test_requires_login(self, client_db):
        resp = client_db.get("/api/v1/wrongbook")
        assert resp.status_code == 401
        assert resp.json()["code"] == 4003

    def test_empty_when_no_wrong_answers(self, client_db, db_session, sample_questions):
        headers, user_id = login_user(client_db, "dev_wb_empty")
        quiz = make_quiz_record(db_session, user_id, sample_questions)
        make_answer_record(db_session, quiz, user_id, sample_questions[0], True)

        resp = client_db.get("/api/v1/wrongbook", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["data"] == {"total": 0, "items": []}

    def test_lists_wrong_items_with_detail(self, client_db, db_session, sample_questions):
        headers, user_id = login_user(client_db, "dev_wb_list")
        quiz = make_quiz_record(db_session, user_id, sample_questions, title="RAG 入门")
        make_answer_record(db_session, quiz, user_id, sample_questions[0], True)
        make_answer_record(
            db_session, quiz, user_id, sample_questions[1], False, selected_answers=["C"]
        )

        resp = client_db.get("/api/v1/wrongbook", headers=headers)

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        item = data["items"][0]
        assert item["quiz_id"] == quiz.quiz_id
        assert item["question_id"] == sample_questions[1].id
        assert item["stem"] == sample_questions[1].stem
        assert item["type"] == "multiple"
        assert item["answer"] == sample_questions[1].answer
        assert item["explanation"] == sample_questions[1].explanation
        assert item["knowledge_point"] == sample_questions[1].knowledge_point
        assert item["wrong_count"] == 1
        assert item["last_wrong_answers"] == ["C"]

    def test_redo_correct_removes_from_list(self, client_db, db_session, sample_questions):
        headers, user_id = login_user(client_db, "dev_wb_clear")
        quiz = make_quiz_record(db_session, user_id, sample_questions)
        make_answer_record(db_session, quiz, user_id, sample_questions[0], False)

        resp = submit_redo(client_db, headers, quiz.quiz_id, "q1", correct=True, selected=["A"])
        assert resp.status_code == 200
        assert resp.json()["data"]["remaining"] == 0

        items = client_db.get("/api/v1/wrongbook", headers=headers).json()["data"]
        assert items["total"] == 0

    def test_redo_wrong_increments_count_and_keeps_item(self, client_db, db_session, sample_questions):
        headers, user_id = login_user(client_db, "dev_wb_keep")
        quiz = make_quiz_record(db_session, user_id, sample_questions)
        make_answer_record(db_session, quiz, user_id, sample_questions[0], False, selected_answers=["B"])

        resp = submit_redo(client_db, headers, quiz.quiz_id, "q1", correct=False, selected=["C"])

        assert resp.status_code == 200
        assert resp.json()["data"]["remaining"] == 1
        items = client_db.get("/api/v1/wrongbook", headers=headers).json()["data"]
        assert items["total"] == 1
        assert items["items"][0]["wrong_count"] == 2
        assert items["items"][0]["last_wrong_answers"] == ["C"]

    def test_latest_redo_wins(self, client_db, db_session, sample_questions):
        """先答对（清理）后又答错 -> 重新回到错题本。"""
        headers, user_id = login_user(client_db, "dev_wb_latest")
        quiz = make_quiz_record(db_session, user_id, sample_questions)
        make_answer_record(db_session, quiz, user_id, sample_questions[0], False)

        submit_redo(client_db, headers, quiz.quiz_id, "q1", correct=True, selected=["A"])
        submit_redo(client_db, headers, quiz.quiz_id, "q1", correct=False, selected=["D"])

        items = client_db.get("/api/v1/wrongbook", headers=headers).json()["data"]
        assert items["total"] == 1
        assert items["items"][0]["wrong_count"] == 2  # 原始 1 次 + 重做错 1 次
        assert items["items"][0]["last_wrong_answers"] == ["D"]


class TestRedoSubmit:
    def test_requires_login(self, client_db):
        resp = client_db.post(
            "/api/v1/wrongbook/redo",
            json={"quiz_id": "quiz_x", "question_id": "q1", "selected_answers": ["A"], "is_correct": True, "duration_ms": 0},
        )
        assert resp.status_code == 401

    def test_quiz_not_found(self, client_db):
        headers, _ = login_user(client_db, "dev_redo_404")
        resp = submit_redo(client_db, headers, "quiz_not_exists", "q1", correct=True)
        assert resp.status_code == 404
        assert resp.json()["code"] == 4005

    def test_question_not_in_quiz_rejected(self, client_db, db_session, sample_questions):
        headers, user_id = login_user(client_db, "dev_redo_badq")
        quiz = make_quiz_record(db_session, user_id, sample_questions)
        resp = submit_redo(client_db, headers, quiz.quiz_id, "q_not_in_quiz", correct=True)
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000
