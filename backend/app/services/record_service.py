"""答题记录服务（阶段 3）：题库落库 / 进度保存 / 提交 / 未完成查询 / 报告落库。

设计要点：
- 幂等：progress / submit 均为“先删后插”全量覆盖，重复调用结果一致
- 容错：与题库无法匹配的 question_id 跳过（记日志）；重复 question_id 去重（后值覆盖前值）；
  current_index 夹取到 [0, total]——用户进度宁可少存脏数据，也不整批丢失
- 归属校验：quiz 必须存在且属于当前用户，否则 4005（HTTP 404）
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizException
from app.models.auth import ContinueLearning
from app.models.progress import QuizProgressData, QuizSubmitData, UnfinishedQuizData
from app.models.quiz import QuizGenerateData
from app.models.records import Answer, Quiz, Report
from app.models.report import AnswerRecord, ReportData

logger = logging.getLogger(__name__)


def _get_owned_quiz(session: Session, user_id: int, quiz_id: str) -> Quiz:
    """取当前用户拥有的闯关；不存在或不属于该用户 -> 4005（HTTP 404）。"""
    quiz = session.scalars(select(Quiz).where(Quiz.quiz_id == quiz_id)).one_or_none()
    if quiz is None or quiz.user_id != user_id:
        raise BizException(code=4005, message="闯关不存在或不属于当前用户", http_status=404)
    return quiz


def _find_latest_doing(session: Session, user_id: int) -> Quiz | None:
    """最近更新的进行中（doing）闯关。"""
    return session.scalars(
        select(Quiz)
        .where(Quiz.user_id == user_id, Quiz.status == "doing")
        .order_by(Quiz.updated_at.desc(), Quiz.id.desc())
    ).first()


def save_generated_quiz(session: Session, user_id: int, data: QuizGenerateData) -> None:
    """生成题库后落库（status=doing），供后续进度保存与续答。"""
    session.add(
        Quiz(
            quiz_id=data.quiz_id,
            user_id=user_id,
            title=data.title,
            summary=data.summary,
            source_type="text",
            questions=[q.model_dump() for q in data.questions],
            status="doing",
            current_index=0,
        )
    )
    session.commit()


def _replace_answers(session: Session, quiz: Quiz, records: list[AnswerRecord]) -> int:
    """全量覆盖该闯关的作答明细；返回实际保存条数。

    - 未知 question_id：跳过（记 warning）
    - 重复 question_id：去重，后值覆盖前值（保持首次出现顺序）
    """
    question_map = {item["id"]: item for item in quiz.questions}
    deduped: dict[str, AnswerRecord] = {}
    for rec in records:
        if rec.question_id not in question_map:
            logger.warning("跳过未知题目：quiz=%s question=%s", quiz.quiz_id, rec.question_id)
            continue
        deduped[rec.question_id] = rec

    session.execute(delete(Answer).where(Answer.quiz_id == quiz.quiz_id))
    for question_id, rec in deduped.items():
        question = question_map[question_id]
        session.add(
            Answer(
                quiz_id=quiz.quiz_id,
                user_id=quiz.user_id,
                question_id=question_id,
                question_type=question["type"],
                knowledge_point=question.get("knowledge_point", ""),
                selected_answers=list(rec.selected_answers),
                is_correct=rec.is_correct,
                duration_ms=rec.duration_ms,
            )
        )
    return len(deduped)


def save_progress(
    session: Session,
    user_id: int,
    quiz_id: str,
    current_index: int,
    records: list[AnswerRecord],
) -> QuizProgressData:
    """保存中途进度：answers 全量覆盖 + current_index 更新（幂等）。"""
    quiz = _get_owned_quiz(session, user_id, quiz_id)
    saved_count = _replace_answers(session, quiz, records)
    quiz.current_index = max(0, min(current_index, len(quiz.questions)))
    session.commit()
    return QuizProgressData(current_index=quiz.current_index, saved_count=saved_count)


def submit_quiz(session: Session, user_id: int, quiz_id: str, records: list[AnswerRecord]) -> QuizSubmitData:
    """提交完整作答：answers 定稿 + quiz 置 done（幂等）。"""
    quiz = _get_owned_quiz(session, user_id, quiz_id)
    saved_count = _replace_answers(session, quiz, records)
    quiz.status = "done"
    quiz.current_index = len(quiz.questions)
    quiz.completed_at = datetime.now()
    session.commit()
    return QuizSubmitData(quiz_id=quiz.quiz_id, status="done", answered_count=saved_count)


def get_unfinished_quiz(session: Session, user_id: int) -> UnfinishedQuizData | None:
    """最近未完成闯关（含完整题库与已答记录）；无则 None。"""
    quiz = _find_latest_doing(session, user_id)
    if quiz is None:
        return None

    answers = session.scalars(select(Answer).where(Answer.quiz_id == quiz.quiz_id).order_by(Answer.id)).all()
    return UnfinishedQuizData(
        quiz_id=quiz.quiz_id,
        title=quiz.title,
        summary=quiz.summary,
        questions=quiz.questions,
        current_index=quiz.current_index,
        records=[
            AnswerRecord(
                question_id=item.question_id,
                selected_answers=item.selected_answers,
                is_correct=item.is_correct,
                duration_ms=item.duration_ms,
            )
            for item in answers
        ],
        total=len(quiz.questions),
        updated_at=quiz.updated_at,
    )


def get_continue_summary(session: Session, user_id: int) -> ContinueLearning | None:
    """续答摘要（个人中心“继续学习”卡片用）；无进行中闯关则 None。"""
    quiz = _find_latest_doing(session, user_id)
    if quiz is None:
        return None
    return ContinueLearning(
        quiz_id=quiz.quiz_id,
        title=quiz.title,
        current_index=quiz.current_index,
        total=len(quiz.questions),
    )


def save_report(session: Session, user_id: int, quiz_id: str, content: ReportData) -> None:
    """报告落库：仅当 quiz_id 非空且归属当前用户时写入；否则跳过（兼容匿名 / 调试）。"""
    if not quiz_id:
        return
    quiz = session.scalars(select(Quiz).where(Quiz.quiz_id == quiz_id)).one_or_none()
    if quiz is None or quiz.user_id != user_id:
        logger.info("报告未落库（quiz 不存在或不属于当前用户）：quiz_id=%s user_id=%s", quiz_id, user_id)
        return
    session.add(Report(quiz_id=quiz_id, user_id=user_id, content=content.model_dump()))
    session.commit()
