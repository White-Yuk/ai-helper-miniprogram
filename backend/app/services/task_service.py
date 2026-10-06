"""异步生成任务服务：创建 / 提交 / 执行 / 查询（对齐 design.md D4）。

设计要点：
- 任务持久化（generation_tasks 表）；创建即返回，应用级线程池后台执行；
- 状态机 pending → running → done / failed；业务异常错误码原样保留（如 4006），
  未知异常兜底 4001；
- 任务线程使用独立数据库会话；步骤写入器每次更新打开短会话；
- 兜底：create_task 懒清理超 TTL 任务；服务启动时残留 pending/running → failed；
- 测试可 patch：_execute_generation（默认真实编排）/ _save_user_record / get_session_factory。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.exceptions import BizException
from app.models.quiz import QuizGenerateData, QuizGenerateRequest
from app.models.task import GenerationTask
from app.services import record_service
from app.services.knowledge_agent import StepCallback
from app.utils.id_generator import new_task_id

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    """应用级线程池（延迟创建，并发数取配置 task_worker_concurrency）。"""
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=get_settings().task_worker_concurrency,
            thread_name_prefix="quiz-task",
        )
    return _executor


# ---- 创建与提交 ----


def _cleanup_expired(session: Session) -> int:
    """懒清理：删除创建时间超过 TTL（默认 24h）的任务。"""
    ttl_hours = get_settings().task_ttl_hours
    threshold = datetime.now() - timedelta(hours=ttl_hours)
    result = session.execute(delete(GenerationTask).where(GenerationTask.created_at < threshold))
    session.commit()
    removed = result.rowcount or 0
    if removed:
        logger.info("任务懒清理：删除 %s 个超期任务（TTL %sh）", removed, ttl_hours)
    return removed


def create_task(session: Session, request: QuizGenerateRequest, user_id: int | None) -> GenerationTask:
    """创建任务（status=pending）并完成懒清理；调用方随后调用 submit_task 提交执行。"""
    _cleanup_expired(session)
    task = GenerationTask(
        task_id=new_task_id(),
        user_id=user_id,
        status="pending",
        request=request.model_dump(mode="json"),
        steps=[],
    )
    session.add(task)
    session.commit()
    session.refresh(task)
    logger.info("创建生成任务：%s（user_id=%s）", task.task_id, user_id)
    return task


def submit_task(task_id: str) -> None:
    """提交任务到应用级线程池执行（接口测试 patch 本函数防止真实执行）。"""
    try:
        _get_executor().submit(_run_task, task_id)
    except Exception:  # noqa: BLE001 - 提交失败不向外抛（任务已持久化，由前端超时兜底）
        logger.exception("任务提交失败：%s", task_id)


# ---- 执行 ----


def _execute_generation(
    request: QuizGenerateRequest,
    user_id: int | None,
    on_step: StepCallback | None = None,
) -> QuizGenerateData:
    """默认执行实现：构建出题链并走带知识获取的编排。

    测试 patch 本函数以离线验证任务状态机（不触真实 LLM / 网络）。
    """
    from app.llm.quiz_chain import build_quiz_chain
    from app.services.quiz_service import generate_quiz_with_grounding

    return generate_quiz_with_grounding(
        request,
        build_quiz_chain(),
        on_step=on_step,
        user_id=user_id,
        fallback_chain=build_quiz_chain(structured_method="json_mode"),
    )


def _save_user_record(user_id: int, data: QuizGenerateData) -> None:
    """登录用户题库入库（独立短会话；失败不影响任务结果）。"""
    session = get_session_factory()()
    try:
        record_service.save_generated_quiz(session, user_id, data)
    finally:
        session.close()


def _finish_failed(session: Session, task: GenerationTask, code: int, message: str) -> None:
    task.status = "failed"
    task.error_code = code
    task.error_message = message
    task.finished_at = datetime.now()
    session.commit()


def _run_task(task_id: str) -> None:
    """任务线程主流程：pending → running → done / failed。"""
    session = get_session_factory()()
    try:
        task = session.scalars(select(GenerationTask).where(GenerationTask.task_id == task_id)).one_or_none()
        if task is None:
            logger.warning("任务不存在（可能已被清理）：%s", task_id)
            return
        task.status = "running"
        session.commit()

        step_writer = make_step_writer(task_id)
        try:
            request = QuizGenerateRequest(**task.request)
            data = _execute_generation(request, task.user_id, on_step=step_writer)
        except BizException as exc:
            # 业务异常：错误码原样保留（如 4006 知识盲区）
            _finish_failed(session, task, exc.code, exc.message)
            return
        except Exception:  # noqa: BLE001 - 未知异常兜底 4001
            logger.exception("任务执行异常：%s", task_id)
            _finish_failed(session, task, 4001, "题库生成失败，请稍后重试")
            return

        if task.user_id is not None:
            try:
                _save_user_record(task.user_id, data)
            except Exception:  # noqa: BLE001 - 入库失败不影响任务结果
                logger.exception("任务题库入库失败（不影响结果）：%s", task_id)

        task.status = "done"
        task.result = data.model_dump(mode="json")
        task.finished_at = datetime.now()
        session.commit()
        logger.info("任务完成：%s", task_id)
    finally:
        session.close()


# ---- 查询 ----


def get_task(session: Session, task_id: str, user_id: int | None) -> GenerationTask:
    """查询任务并做归属校验：不存在 / 归属不符 → 4005（HTTP 404）。

    - 匿名任务（user_id 为空）：凭随机任务号读取（任务号即凭证）
    - 登录任务：仅归属用户可读取
    """
    task = session.scalars(select(GenerationTask).where(GenerationTask.task_id == task_id)).one_or_none()
    if task is None:
        raise BizException(code=4005, message="任务不存在或已过期", http_status=404)
    if task.user_id is not None and task.user_id != user_id:
        raise BizException(code=4005, message="任务不存在或已过期", http_status=404)
    return task


# ---- 步骤写入 ----


def make_step_writer(task_id: str) -> StepCallback:
    """生成步骤写入器（upsert 语义：key 相同则更新，否则追加）。

    每次更新打开短会话；写入失败只记 warning，不影响任务主流程。
    """

    def _write(key: str, label: str, detail: str, state: str) -> None:
        session = get_session_factory()()
        try:
            task = session.scalars(
                select(GenerationTask).where(GenerationTask.task_id == task_id)
            ).one_or_none()
            if task is None:
                return
            steps = [dict(step) for step in (task.steps or [])]
            now = datetime.now().isoformat(timespec="seconds")
            for step in steps:
                if step.get("key") == key:
                    step.update({"label": label, "detail": detail, "state": state, "ts": now})
                    break
            else:
                steps.append({"key": key, "label": label, "detail": detail, "state": state, "ts": now})
            task.steps = steps  # 整体替换，确保 SQLAlchemy 检测到变更
            session.commit()
        except Exception:  # noqa: BLE001 - 步骤写入失败不影响任务主流程
            logger.warning("任务步骤写入失败：task=%s key=%s", task_id, key, exc_info=True)
            session.rollback()
        finally:
            session.close()

    return _write


# ---- 启动兜底 ----


def mark_stale_tasks_failed() -> int:
    """服务启动兜底：把残留的 pending / running 任务标记为 failed（避免客户端无限轮询）。

    返回处理条数；任何异常只记日志（不影响服务启动）。
    """
    session = get_session_factory()()
    try:
        tasks = session.scalars(
            select(GenerationTask).where(GenerationTask.status.in_(["pending", "running"]))
        ).all()
        if not tasks:
            return 0
        now = datetime.now()
        for task in tasks:
            task.status = "failed"
            task.error_code = 4001
            task.error_message = "生成任务中断，请重新发起"
            task.finished_at = now
        session.commit()
        logger.warning("启动清理：%s 个残留生成任务标记为失败", len(tasks))
        return len(tasks)
    except Exception:  # noqa: BLE001 - 清理失败不影响服务启动
        logger.warning("启动清理生成任务失败（不影响服务启动）", exc_info=True)
        session.rollback()
        return 0
    finally:
        session.close()
