"""报告接口测试：成功路径、参数校验、失败兜底、阶段 3 落库。"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.v1.routes.report import get_report_chain
from tests.conftest import FakeChain, login_headers


def make_payload() -> dict:
    return {
        "quiz_id": "quiz_test",
        "topic": "RAG 入门",
        "questions": [
            {
                "id": "q1",
                "type": "single",
                "stem": "RAG 主要解决什么问题？",
                "options": [{"key": "A", "text": "知识过时"}, {"key": "B", "text": "速度慢"}],
                "answer": ["A"],
                "explanation": "讲解",
                "knowledge_point": "核心概念",
                "difficulty": "easy",
            }
        ],
        "answer_records": [
            {"question_id": "q1", "selected_answers": ["B"], "is_correct": False, "duration_ms": 3200}
        ],
    }


VALID_REPORT_LLM = {
    "mastered_points": ["核心概念"],
    "weak_points": ["应用场景"],
    "three_line_summary": ["一", "二", "三"],
    "advice": ["建议"],
    "share_quote": "把知识做成关卡，记忆会更深。",
}


class _FakeStructuredChain:
    """返回 dict 的简单 chain（模拟 LangChain 结构化输出的 Pydantic 对象）。

    report_service 会把 chain 返回的对象视为 ReportLlmOutput；
    这里用 mock 对象也可，但为了贴近真实返回，直接用 pydantic 构造。
    """

    def __init__(self):
        from app.models.report import ReportLlmOutput

        self.result = ReportLlmOutput(**VALID_REPORT_LLM)
        self.calls = []

    def invoke(self, inputs):
        self.calls.append(inputs)
        return self.result


class TestReportGenerateApi:
    def test_success(self, app, client):
        app.dependency_overrides[get_report_chain] = lambda: _FakeStructuredChain()

        resp = client.post("/api/v1/report/generate", json=make_payload())

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["accuracy"] == 0  # 1 题答错 -> 0%
        assert data["share_quote"]
        assert data["three_line_summary"] == ["一", "二", "三"]

    def test_validation_error(self, client):
        resp = client.post("/api/v1/report/generate", json={**make_payload(), "topic": ""})
        assert resp.status_code == 422
        body = resp.json()
        assert body["code"] == 4000
        assert body["data"] is None

    def test_empty_records_rejected(self, client):
        resp = client.post("/api/v1/report/generate", json={**make_payload(), "answer_records": []})
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000

    def test_llm_failure_returns_biz_error(self, app, client):
        app.dependency_overrides[get_report_chain] = lambda: FakeChain([RuntimeError("mock down")])

        resp = client.post("/api/v1/report/generate", json=make_payload())

        assert resp.status_code == 502
        body = resp.json()
        assert body["code"] == 4002
        assert body["data"] is None


@pytest.mark.usefixtures("auth_settings")
class TestReportPersist:
    """阶段 3：带 token 且 quiz 归属本人时，报告落库（reports）。"""

    GENERATE_PAYLOAD = {
        "user_input": "什么是 RAG？",
        "question_count": 4,
        "difficulty": "mixed",
        "question_types": ["single", "multiple", "judge", "fill"],
    }

    @staticmethod
    def _generate_quiz(app, client, headers, sample_quiz_data) -> str:
        from app.api.v1.routes.quiz import get_quiz_chain

        app.dependency_overrides[get_quiz_chain] = lambda: FakeChain([sample_quiz_data])
        resp = client.post("/api/v1/quiz/generate", json=TestReportPersist.GENERATE_PAYLOAD, headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()["data"]["quiz_id"]

    @staticmethod
    def _report_payload(quiz_id: str, sample_quiz_data) -> dict:
        return {
            "quiz_id": quiz_id,
            "topic": sample_quiz_data.title,
            "questions": [q.model_dump() for q in sample_quiz_data.questions],
            "answer_records": [
                {"question_id": q.id, "selected_answers": q.answer, "is_correct": True, "duration_ms": 1200}
                for q in sample_quiz_data.questions
            ],
        }

    def test_report_persisted_for_owned_quiz(self, app, client_db, db_session, sample_quiz_data):
        from app.models.records import Report

        headers = login_headers(client_db, "device_report")
        quiz_id = self._generate_quiz(app, client_db, headers, sample_quiz_data)
        app.dependency_overrides[get_report_chain] = lambda: _FakeStructuredChain()

        resp = client_db.post(
            "/api/v1/report/generate", json=self._report_payload(quiz_id, sample_quiz_data), headers=headers
        )

        assert resp.status_code == 200, resp.text
        reports = db_session.scalars(select(Report)).all()
        assert len(reports) == 1
        assert reports[0].quiz_id == quiz_id
        assert reports[0].content["accuracy"] == 100
        assert reports[0].content["share_quote"] == "把知识做成关卡，记忆会更深。"

    def test_report_not_persisted_when_anonymous(self, app, client_db, db_session):
        from app.models.records import Report

        app.dependency_overrides[get_report_chain] = lambda: _FakeStructuredChain()

        resp = client_db.post("/api/v1/report/generate", json=make_payload())

        assert resp.status_code == 200
        assert db_session.scalars(select(Report)).all() == []

    def test_report_not_persisted_for_other_users_quiz(self, app, client_db, db_session, sample_quiz_data):
        from app.models.records import Report

        owner_headers = login_headers(client_db, "device_owner")
        quiz_id = self._generate_quiz(app, client_db, owner_headers, sample_quiz_data)
        other_headers = login_headers(client_db, "device_intruder")
        app.dependency_overrides[get_report_chain] = lambda: _FakeStructuredChain()

        resp = client_db.post(
            "/api/v1/report/generate", json=self._report_payload(quiz_id, sample_quiz_data), headers=other_headers
        )

        assert resp.status_code == 200  # 报告正常返回，但跳过落库
        assert db_session.scalars(select(Report)).all() == []
