"""阶段 5：学习报表与知识掌握详情服务。

口径说明：
- 趋势按 answers.created_at 的本地日期聚合；week=本周一~周日、month=本月 1 日~今天、all=最早答题日~今天（最多回溯 90 天）
- overall_accuracy 仅统计所选范围内数据；无数据为 None
- domains（各领域掌握度）为累计口径（不受范围影响），按最近更新的闯关取前 5 个
- 知识掌握详情中，知识点正确率 = 答对数 / 已作答数；未作答 = unlearned
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BizException
from app.models.auth import UserStats
from app.models.records import Answer, Quiz
from app.models.stats import (
    DomainStat,
    KnowledgeDetailData,
    KnowledgePointStat,
    StatsData,
    TrendPoint,
)

MAX_ALL_DAYS = 90  # all 视图最多回溯天数，避免超长空序列
DOMAIN_LIMIT = 5  # 领域掌握度最多展示的闯关数


def _calc_accuracy(correct: int, total: int) -> int:
    return round(correct / total * 100) if total else 0


def get_user_overview(session: Session, user_id: int) -> UserStats:
    """个人中心统计三宫格：闯关数（含进行中）/ 累计答题数 / 平均正确率（0-100）。"""
    quiz_count = len(session.scalars(select(Quiz.id).where(Quiz.user_id == user_id)).all())
    answers = session.scalars(select(Answer).where(Answer.user_id == user_id)).all()
    correct = sum(1 for item in answers if item.is_correct)
    return UserStats(
        quiz_count=quiz_count,
        answered_count=len(answers),
        avg_accuracy=_calc_accuracy(correct, len(answers)),
    )


def get_user_stats(session: Session, user_id: int, range_: str) -> StatsData:
    """学习报表：整体正确率 + 按天趋势 + 各领域掌握度。"""
    today = date.today()
    if range_ == "week":
        start = today - timedelta(days=today.weekday())  # 本周一
        end = start + timedelta(days=6)  # 本周日
    elif range_ == "month":
        start = today.replace(day=1)
        end = today
    else:  # all
        first = session.scalars(select(func.min(Answer.created_at)).where(Answer.user_id == user_id)).first()
        start = first.date() if first else today
        start = max(start, today - timedelta(days=MAX_ALL_DAYS - 1))
        end = today

    answers = session.scalars(select(Answer).where(Answer.user_id == user_id).order_by(Answer.id)).all()

    ranged = [item for item in answers if start <= item.created_at.date() <= end]

    overall = None
    if ranged:
        overall = _calc_accuracy(sum(1 for item in ranged if item.is_correct), len(ranged))

    by_day: dict[date, list] = {}
    for item in ranged:
        by_day.setdefault(item.created_at.date(), []).append(item)

    trend: list[TrendPoint] = []
    cursor = start
    while cursor <= end:
        day_answers = by_day.get(cursor, [])
        total = len(day_answers)
        correct = sum(1 for item in day_answers if item.is_correct)
        trend.append(
            TrendPoint(
                date=cursor.isoformat(),
                total=total,
                correct=correct,
                accuracy=_calc_accuracy(correct, total) if total else None,
            )
        )
        cursor += timedelta(days=1)

    # 各领域掌握度：累计口径，按最近更新的闯关取前 N 个（只保留有作答记录的）
    answer_by_quiz: dict[str, list] = {}
    for item in answers:
        answer_by_quiz.setdefault(item.quiz_id, []).append(item)

    quizzes = session.scalars(
        select(Quiz)
        .where(Quiz.user_id == user_id)
        .order_by(Quiz.updated_at.desc(), Quiz.id.desc())
        .limit(DOMAIN_LIMIT)
    ).all()
    domains: list[DomainStat] = []
    for quiz in quizzes:
        quiz_answers = answer_by_quiz.get(quiz.quiz_id)
        if not quiz_answers:
            continue
        correct = sum(1 for item in quiz_answers if item.is_correct)
        domains.append(
            DomainStat(
                quiz_id=quiz.quiz_id,
                name=quiz.title,
                total=len(quiz_answers),
                correct=correct,
                accuracy=_calc_accuracy(correct, len(quiz_answers)),
            )
        )

    return StatsData(range=range_, overall_accuracy=overall, trend=trend, domains=domains)


def get_knowledge_detail(session: Session, user_id: int, quiz_id: str) -> KnowledgeDetailData:
    """知识掌握详情：知识点清单（掌握 / 薄弱 / 未学）。"""
    quiz = session.scalars(select(Quiz).where(Quiz.quiz_id == quiz_id)).one_or_none()
    if quiz is None or quiz.user_id != user_id:
        raise BizException(code=4005, message="闯关不存在或不属于当前用户", http_status=404)

    answers = session.scalars(
        select(Answer).where(Answer.user_id == user_id, Answer.quiz_id == quiz_id)
    ).all()
    answer_by_question = {item.question_id: item for item in answers}

    overall = _calc_accuracy(
        sum(1 for item in answers if item.is_correct), len(answers)
    )

    # 按知识点聚合（保持题库中的出现顺序）
    order: list[str] = []
    point_total: dict[str, int] = {}
    point_answered: dict[str, int] = {}
    point_correct: dict[str, int] = {}
    for question in quiz.questions:
        name = question.get("knowledge_point", "")
        if name not in point_total:
            order.append(name)
            point_total[name] = 0
            point_answered[name] = 0
            point_correct[name] = 0
        point_total[name] += 1
        answer = answer_by_question.get(question["id"])
        if answer is not None:
            point_answered[name] += 1
            if answer.is_correct:
                point_correct[name] += 1

    points: list[KnowledgePointStat] = []
    mastered = weak = unlearned = 0
    for name in order:
        answered = point_answered[name]
        correct = point_correct[name]
        if answered == 0:
            state = "unlearned"
            accuracy = 0
            unlearned += 1
        elif correct == answered:
            state = "mastered"
            accuracy = 100
            mastered += 1
        else:
            state = "weak"
            accuracy = _calc_accuracy(correct, answered)
            weak += 1
        points.append(
            KnowledgePointStat(
                name=name,
                total=point_total[name],
                answered=answered,
                correct=correct,
                accuracy=accuracy,
                state=state,
            )
        )

    return KnowledgeDetailData(
        quiz_id=quiz.quiz_id,
        title=quiz.title,
        accuracy=overall,
        total_points=len(order),
        mastered_count=mastered,
        weak_count=weak,
        unlearned_count=unlearned,
        points=points,
    )
