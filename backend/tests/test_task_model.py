"""GenerationTask 模型 schema 测试（任务 3.1）。"""
from __future__ import annotations

from app.models.task import GenerationTask
from app.utils.id_generator import new_task_id


class TestNewTaskId:
    def test_prefix_and_length(self):
        task_id = new_task_id()
        assert task_id.startswith("task_")
        assert len(task_id) == len("task_") + 12

    def test_unique(self):
        assert new_task_id() != new_task_id()


class TestGenerationTaskModel:
    def test_defaults_and_persistence(self, db_session):
        task = GenerationTask(
            task_id=new_task_id(),
            user_id=None,
            request={"user_input": "Harness Engineering", "question_count": 5},
            steps=[],
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.id is not None
        assert task.status == "pending"
        assert task.steps == []
        assert task.result is None
        assert task.error_code is None
        assert task.error_message is None
        assert task.created_at is not None
        assert task.updated_at is not None
        assert task.finished_at is None

    def test_json_fields_roundtrip(self, db_session):
        step = {
            "key": "run-1",
            "label": "联网搜索",
            "detail": "搜索词：x",
            "state": "done",
            "ts": "2026-10-06T10:00:00",
        }
        task = GenerationTask(task_id=new_task_id(), user_id=1, request={"user_input": "x"}, steps=[step])
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        assert task.steps == [step]

        task.result = {"title": "t", "questions": [{"id": "q1"}]}
        task.status = "done"
        task.error_code = 4006
        db_session.commit()
        db_session.refresh(task)
        assert task.result["questions"][0]["id"] == "q1"
        assert task.error_code == 4006
