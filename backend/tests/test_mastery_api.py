"""阶段 5：知识掌握详情接口测试（GET /knowledge-base/{quiz_id}，TDD 先行）。

覆盖：
- 知识点分类：掌握（全对）/ 薄弱（有错）/ 未学（无作答）
- 整体正确率与统计计数
- 归属校验 404、未登录 401
"""
from __future__ import annotations

import pytest

from app.models.quiz import Option, Question
from tests.conftest import login_user, make_answer_record, make_quiz_record

pytestmark = pytest.mark.usefixtures("auth_settings")


def build_questions() -> list[Question]:
    """3 个知识点、4 道题：流程(2题可全对)、场景(1题答错)、区别(1题未答)。"""
    return [
        Question(
            id="q1",
            type="single",
            stem="RAG 的流程第一步是？",
            options=[Option(key="A", text="检索"), Option(key="B", text="微调")],
            answer=["A"],
            explanation="先检索。",
            knowledge_point="基本流程",
            difficulty="easy",
        ),
        Question(
            id="q2",
            type="judge",
            stem="判断：RAG 先检索再生成。",
            options=[],
            answer=["对"],
            explanation="对。",
            knowledge_point="基本流程",
            difficulty="easy",
        ),
        Question(
            id="q3",
            type="single",
            stem="哪个场景适合 RAG？",
            options=[Option(key="A", text="内部知识问答"), Option(key="B", text="训练新模型")],
            answer=["A"],
            explanation="内部问答。",
            knowledge_point="应用场景",
            difficulty="medium",
        ),
        Question(
            id="q4",
            type="judge",
            stem="判断：RAG 等于微调。",
            options=[],
            answer=["错"],
            explanation="不等。",
            knowledge_point="与微调的区别",
            difficulty="hard",
        ),
    ]


class TestKnowledgeDetail:
    def test_requires_login(self, client_db):
        resp = client_db.get("/api/v1/knowledge-base/quiz_any")
        assert resp.status_code == 401

    def test_quiz_not_found(self, client_db):
        headers, _ = login_user(client_db, "dev_mastery_404")
        resp = client_db.get("/api/v1/knowledge-base/quiz_not_exists", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == 4005

    def test_other_users_quiz_rejected(self, client_db, db_session, sample_questions):
        owner_headers, owner_id = login_user(client_db, "dev_mastery_owner")
        quiz = make_quiz_record(db_session, owner_id, sample_questions)
        intruder_headers, _ = login_user(client_db, "dev_mastery_intruder")

        resp = client_db.get(f"/api/v1/knowledge-base/{quiz.quiz_id}", headers=intruder_headers)

        assert resp.status_code == 404

    def test_points_classified_and_counted(self, client_db, db_session):
        """q1/q2 全对 -> 掌握；q3 答错 -> 薄弱；q4 未答 -> 未学。"""
        headers, user_id = login_user(client_db, "dev_mastery_full")
        questions = build_questions()
        quiz = make_quiz_record(db_session, user_id, questions, title="RAG 入门")
        make_answer_record(db_session, quiz, user_id, questions[0], True)
        make_answer_record(db_session, quiz, user_id, questions[1], True)
        make_answer_record(db_session, quiz, user_id, questions[2], False)

        resp = client_db.get(f"/api/v1/knowledge-base/{quiz.quiz_id}", headers=headers)

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["title"] == "RAG 入门"
        assert data["accuracy"] == 67  # 3 题 2 对
        assert data["total_points"] == 3
        assert data["mastered_count"] == 1
        assert data["weak_count"] == 1
        assert data["unlearned_count"] == 1

        points = {point["name"]: point for point in data["points"]}
        # 顺序 = 题库中出现顺序
        assert [point["name"] for point in data["points"]] == ["基本流程", "应用场景", "与微调的区别"]
        assert points["基本流程"]["state"] == "mastered"
        assert points["基本流程"]["accuracy"] == 100
        assert points["应用场景"]["state"] == "weak"
        assert points["应用场景"]["accuracy"] == 0
        assert points["与微调的区别"]["state"] == "unlearned"
        assert points["与微调的区别"]["answered"] == 0

    def test_no_answers_all_unlearned(self, client_db, db_session):
        headers, user_id = login_user(client_db, "dev_mastery_empty")
        quiz = make_quiz_record(db_session, user_id, build_questions())

        resp = client_db.get(f"/api/v1/knowledge-base/{quiz.quiz_id}", headers=headers)

        data = resp.json()["data"]
        assert data["accuracy"] == 0
        assert data["mastered_count"] == 0
        assert data["unlearned_count"] == 3
        assert all(point["state"] == "unlearned" for point in data["points"])
