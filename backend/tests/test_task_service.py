"""任务服务测试（任务 3.3）：创建 / 状态机 / 步骤 / 归属 / 过期清理 / 残留处理。

全部离线：patch `_execute_generation` / `_save_user_record`（不触真实 LLM / 网络），
会话工厂指向 SQLite 临时库（不依赖本机 MySQL）。
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.exceptions import BizException
from app.models.quiz import QuizGenerateData, QuizGenerateRequest
from app.models.task import GenerationTask
from app.services import task_service
from app.utils.id_generator import new_task_id
from tests.conftest import make_question


@pytest.fixture()
def task_factory(tmp_path, monkeypatch):
    """SQLite 临时库 + 覆盖 task_service 的会话工厂。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401  注册全部模型
    from app.core.db import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'task.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(task_service, "get_session_factory", lambda: factory)
    yield factory
    engine.dispose()


def make_request(**overrides) -> QuizGenerateRequest:
    defaults = dict(user_input="Harness Engineering", question_count=3, question_types=["single"])
    defaults.update(overrides)
    return QuizGenerateRequest(**defaults)


def make_quiz_data() -> QuizGenerateData:
    return QuizGenerateData(
        quiz_id="quiz_test0001",
        title="测试题库",
        summary="摘要",
        questions=[make_question(f"q{i}", "single") for i in (1, 2, 3)],
    )


def _get(factory, task_id: str) -> GenerationTask:
    session = factory()
    try:
        return session.scalars(select(GenerationTask).where(GenerationTask.task_id == task_id)).one()
    finally:
        session.close()


class TestCreateTask:
    def test_creates_pending_task(self, task_factory):
        session = task_factory()
        task = task_service.create_task(session, make_request(), user_id=None)
        session.close()

        assert task.task_id.startswith("task_")
        assert task.status == "pending"
        assert task.user_id is None
        assert task.steps == []
        assert task.request["user_input"] == "Harness Engineering"
        assert task.request["question_count"] == 3

    def test_creates_with_user_and_snapshot(self, task_factory):
        session = task_factory()
        task = task_service.create_task(
            session, make_request(user_input="什么是 HTTP", difficulty="easy"), user_id=7
        )
        session.close()

        assert task.user_id == 7
        assert task.request["difficulty"] == "easy"
        assert task.request["user_input"] == "什么是 HTTP"

    def test_lazy_cleanup_removes_expired(self, task_factory):
        session = task_factory()
        expired = GenerationTask(
            task_id=new_task_id(),
            user_id=None,
            status="done",
            request={},
            steps=[],
            created_at=datetime.now() - timedelta(hours=48),
        )
        fresh = GenerationTask(
            task_id=new_task_id(),
            user_id=None,
            status="done",
            request={},
            steps=[],
            created_at=datetime.now() - timedelta(hours=1),
        )
        session.add_all([expired, fresh])
        session.commit()

        task_service.create_task(session, make_request(), None)
        remaining = {t.task_id for t in session.scalars(select(GenerationTask)).all()}
        session.close()

        assert expired.task_id not in remaining
        assert fresh.task_id in remaining


class TestRunTask:
    def test_success_flow_writes_result_and_steps(self, task_factory, monkeypatch):
        session = task_factory()
        task = task_service.create_task(session, make_request(), None)
        session.close()

        captured: dict = {}

        def fake_execute(request, user_id, on_step=None):
            captured["request"] = request
            captured["user_id"] = user_id
            if on_step:
                on_step("tool-1", "联网搜索", "搜索词：Harness", "doing")
                on_step("tool-1", "联网搜索", "获得 2 条资料", "done")
            return make_quiz_data()

        monkeypatch.setattr(task_service, "_execute_generation", fake_execute)
        task_service._run_task(task.task_id)

        done = _get(task_factory, task.task_id)
        assert done.status == "done"
        assert done.finished_at is not None
        assert done.result["title"] == "测试题库"
        assert done.result["quiz_id"] == "quiz_test0001"
        assert done.steps == [
            {
                "key": "tool-1",
                "label": "联网搜索",
                "detail": "获得 2 条资料",
                "state": "done",
                "ts": done.steps[0]["ts"],
            }
        ]
        assert captured["user_id"] is None
        assert captured["request"].user_input == "Harness Engineering"

    def test_logged_user_record_saved(self, task_factory, monkeypatch):
        session = task_factory()
        task = task_service.create_task(session, make_request(), user_id=7)
        session.close()

        saved: list = []
        monkeypatch.setattr(task_service, "_execute_generation", lambda request, user_id, on_step=None: make_quiz_data())
        monkeypatch.setattr(task_service, "_save_user_record", lambda uid, data: saved.append((uid, data.quiz_id)))

        task_service._run_task(task.task_id)

        assert saved == [(7, "quiz_test0001")]
        assert _get(task_factory, task.task_id).status == "done"

    def test_anonymous_skips_record(self, task_factory, monkeypatch):
        session = task_factory()
        task = task_service.create_task(session, make_request(), None)
        session.close()

        called: list = []
        monkeypatch.setattr(task_service, "_execute_generation", lambda request, user_id, on_step=None: make_quiz_data())
        monkeypatch.setattr(task_service, "_save_user_record", lambda uid, data: called.append(uid))

        task_service._run_task(task.task_id)

        assert called == []

    def test_business_error_marks_failed_with_code(self, task_factory, monkeypatch):
        session = task_factory()
        task = task_service.create_task(session, make_request(), None)
        session.close()

        def fake_execute(request, user_id, on_step=None):
            raise BizException(code=4006, message="知识盲区：该主题暂无可靠资料", http_status=502)

        monkeypatch.setattr(task_service, "_execute_generation", fake_execute)
        task_service._run_task(task.task_id)

        failed = _get(task_factory, task.task_id)
        assert failed.status == "failed"
        assert failed.error_code == 4006
        assert failed.error_message == "知识盲区：该主题暂无可靠资料"
        assert failed.result is None
        assert failed.finished_at is not None

    def test_unknown_error_maps_4001(self, task_factory, monkeypatch):
        session = task_factory()
        task = task_service.create_task(session, make_request(), None)
        session.close()

        def fake_execute(request, user_id, on_step=None):
            raise RuntimeError("boom")

        monkeypatch.setattr(task_service, "_execute_generation", fake_execute)
        task_service._run_task(task.task_id)

        failed = _get(task_factory, task.task_id)
        assert failed.status == "failed"
        assert failed.error_code == 4001

    def test_missing_task_is_noop(self, task_factory):
        task_service._run_task("task_not_exists")  # 不抛异常

    def test_record_failure_does_not_fail_task(self, task_factory, monkeypatch):
        session = task_factory()
        task = task_service.create_task(session, make_request(), user_id=7)
        session.close()

        monkeypatch.setattr(task_service, "_execute_generation", lambda request, user_id, on_step=None: make_quiz_data())

        def boom(uid, data):
            raise RuntimeError("db down")

        monkeypatch.setattr(task_service, "_save_user_record", boom)
        task_service._run_task(task.task_id)

        assert _get(task_factory, task.task_id).status == "done"


class TestStepWriter:
    def test_upsert_same_key_and_append_new_key(self, task_factory):
        session = task_factory()
        task = task_service.create_task(session, make_request(), None)
        session.close()

        writer = task_service.make_step_writer(task.task_id)
        writer("a", "联网搜索", "搜索词：x", "doing")
        writer("b", "网页提取", "提取：https://x", "doing")
        writer("a", "联网搜索", "获得 3 条资料", "done")

        reloaded = _get(task_factory, task.task_id)
        assert [step["key"] for step in reloaded.steps] == ["a", "b"]
        assert reloaded.steps[0]["detail"] == "获得 3 条资料"
        assert reloaded.steps[0]["state"] == "done"
        assert reloaded.steps[1]["state"] == "doing"

    def test_missing_task_noop(self, task_factory):
        task_service.make_step_writer("task_none")("k", "l", "d", "doing")  # 不抛异常


class TestGetTask:
    def test_anonymous_task_readable_by_anyone(self, task_factory):
        session = task_factory()
        task = task_service.create_task(session, make_request(), None)
        got_anon = task_service.get_task(session, task.task_id, None)
        got_user = task_service.get_task(session, task.task_id, 5)
        session.close()
        assert got_anon.task_id == task.task_id
        assert got_user.task_id == task.task_id

    def test_owner_mismatch_4005(self, task_factory):
        session = task_factory()
        task = task_service.create_task(session, make_request(), user_id=7)
        with pytest.raises(BizException) as err:
            task_service.get_task(session, task.task_id, 8)
        with pytest.raises(BizException):
            task_service.get_task(session, task.task_id, None)
        session.close()
        assert err.value.code == 4005

    def test_missing_4005(self, task_factory):
        session = task_factory()
        with pytest.raises(BizException) as err:
            task_service.get_task(session, "task_not_exists", None)
        session.close()
        assert err.value.code == 4005


class TestStaleCleanup:
    def test_marks_pending_and_running_failed(self, task_factory):
        session = task_factory()
        session.add_all(
            [
                GenerationTask(task_id=new_task_id(), user_id=None, status="pending", request={}, steps=[]),
                GenerationTask(task_id=new_task_id(), user_id=None, status="running", request={}, steps=[]),
                GenerationTask(task_id=new_task_id(), user_id=None, status="done", request={}, steps=[], result={"x": 1}),
            ]
        )
        session.commit()
        session.close()

        count = task_service.mark_stale_tasks_failed()

        assert count == 2
        session = task_factory()
        failed = session.scalars(select(GenerationTask).where(GenerationTask.status == "failed")).all()
        done = session.scalars(select(GenerationTask).where(GenerationTask.status == "done")).all()
        session.close()
        assert len(failed) == 2
        assert len(done) == 1
        assert all(t.error_code == 4001 and t.finished_at is not None for t in failed)

    def test_nothing_to_clean_returns_zero(self, task_factory):
        assert task_service.mark_stale_tasks_failed() == 0
