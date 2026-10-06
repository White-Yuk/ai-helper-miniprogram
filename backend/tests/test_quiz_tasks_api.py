"""任务接口测试（任务 7.2）：创建 / 查询各状态 / 归属校验 / 4005。

说明：
- patch `task_service.submit_task` 防止测试中真实执行（线程池 / LLM / 网络）；
- 数据库走 client_db（SQLite 临时库覆盖 get_db）。
"""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.task import GenerationTask
from app.services import task_service
from app.utils.id_generator import new_task_id
from tests.conftest import login_headers

pytestmark = pytest.mark.usefixtures("auth_settings")

VALID_PAYLOAD = {
    "user_input": "什么是 RAG？",
    "question_count": 4,
    "difficulty": "mixed",
    "question_types": ["single", "multiple", "judge", "fill"],
}


@pytest.fixture()
def submitted(monkeypatch) -> list:
    """捕获提交调用（防止测试中真实执行任务）。"""
    ids: list = []
    monkeypatch.setattr(task_service, "submit_task", lambda task_id: ids.append(task_id))
    return ids


def make_task(db_session, **overrides) -> GenerationTask:
    defaults = dict(task_id=new_task_id(), user_id=None, status="pending", request={}, steps=[])
    defaults.update(overrides)
    task = GenerationTask(**defaults)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


class TestCreateTaskApi:
    def test_creates_and_submits(self, client_db, db_session, submitted):
        resp = client_db.post("/api/v1/quiz/tasks", json=VALID_PAYLOAD)

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        assert data["task_id"].startswith("task_")
        assert data["status"] == "pending"
        assert submitted == [data["task_id"]]

        row = db_session.scalars(
            select(GenerationTask).where(GenerationTask.task_id == data["task_id"])
        ).one()
        assert row.user_id is None
        assert row.request["user_input"] == "什么是 RAG？"

    def test_validation_error_wrapped(self, client_db, submitted):
        resp = client_db.post("/api/v1/quiz/tasks", json={**VALID_PAYLOAD, "user_input": "   "})

        assert resp.status_code == 422
        assert resp.json()["code"] == 4000
        assert submitted == []

    def test_logged_in_task_belongs_to_user(self, client_db, db_session, submitted):
        headers = login_headers(client_db, "device_task_owner")
        resp = client_db.post("/api/v1/quiz/tasks", json=VALID_PAYLOAD, headers=headers)

        assert resp.status_code == 200
        task_id = resp.json()["data"]["task_id"]
        row = db_session.scalars(select(GenerationTask).where(GenerationTask.task_id == task_id)).one()
        assert row.user_id is not None


class TestGetTaskApi:
    def test_pending_task(self, client_db, db_session):
        task = make_task(db_session)

        resp = client_db.get(f"/api/v1/quiz/tasks/{task.task_id}")

        assert resp.status_code == 200
        assert resp.json()["data"] == {
            "task_id": task.task_id,
            "status": "pending",
            "steps": [],
            "result": None,
            "error": None,
        }

    def test_running_task_with_steps(self, client_db, db_session):
        steps = [
            {"key": "run-1", "label": "联网搜索", "detail": "获得 3 条资料", "state": "done", "ts": "t"},
            {"key": "stage:generate", "label": "AI 出题", "detail": "正在生成题目", "state": "doing", "ts": "t"},
        ]
        task = make_task(db_session, status="running", steps=steps)

        resp = client_db.get(f"/api/v1/quiz/tasks/{task.task_id}")

        assert resp.json()["data"]["status"] == "running"
        assert resp.json()["data"]["steps"] == steps

    def test_done_task_with_result(self, client_db, db_session):
        task = make_task(db_session, status="done", result={"title": "RAG 入门", "sources": []})

        resp = client_db.get(f"/api/v1/quiz/tasks/{task.task_id}")

        data = resp.json()["data"]
        assert data["status"] == "done"
        assert data["result"]["title"] == "RAG 入门"
        assert data["error"] is None

    def test_failed_task_with_4006(self, client_db, db_session):
        task = make_task(db_session, status="failed", error_code=4006, error_message="知识盲区")

        resp = client_db.get(f"/api/v1/quiz/tasks/{task.task_id}")

        data = resp.json()["data"]
        assert data["status"] == "failed"
        assert data["result"] is None
        assert data["error"] == {"code": 4006, "message": "知识盲区"}

    def test_missing_task_4005(self, client_db):
        resp = client_db.get("/api/v1/quiz/tasks/task_not_exists")

        assert resp.status_code == 404
        assert resp.json()["code"] == 4005

    def test_owned_task_not_readable_anonymously(self, client_db, db_session):
        task = make_task(db_session, user_id=999999)

        resp = client_db.get(f"/api/v1/quiz/tasks/{task.task_id}")

        assert resp.status_code == 404
        assert resp.json()["code"] == 4005

    def test_owned_task_readable_by_owner(self, client_db, db_session):
        headers = login_headers(client_db, "device_task_reader")
        me = client_db.get("/api/v1/me", headers=headers).json()["data"]
        task = make_task(db_session, user_id=me["id"])

        resp = client_db.get(f"/api/v1/quiz/tasks/{task.task_id}", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["data"]["task_id"] == task.task_id
