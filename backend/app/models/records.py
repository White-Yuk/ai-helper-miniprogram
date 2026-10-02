"""学习记录 ORM（阶段 3）：闯关题库 / 作答明细 / 复盘报告。

说明：
- quizzes.questions 与 reports.content 使用 JSON 列存储（MySQL JSON / SQLite JSON 均兼容）
- answers 在“保存进度 / 提交作答”时按 quiz 全量覆盖，保证幂等（以本次提交为准）
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Quiz(Base):
    """闯关题库：一次 AI 生成对应一条记录，承载用户的作答生命周期。"""

    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quiz_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(String(500), default="")
    source_type: Mapped[str] = mapped_column(String(16), default="text")
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    # doing / done
    status: Mapped[str] = mapped_column(String(8), default="doing")
    current_index: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)


class Answer(Base):
    """单题作答明细：progress / submit 均按 quiz 全量覆盖。"""

    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quiz_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    question_id: Mapped[str] = mapped_column(String(64))
    question_type: Mapped[str] = mapped_column(String(16))
    knowledge_point: Mapped[str] = mapped_column(String(255), default="")
    selected_answers: Mapped[list[str]] = mapped_column(JSON)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Report(Base):
    """复盘报告落库：content 为完整报告 JSON（accuracy + 文字分析）。"""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    quiz_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class RedoRecord(Base):
    """错题重做记录（阶段 6）：每次重做追加一条，用于错题本“清理”判定。

    - 某题最近一次重做答对 -> 从错题本移除（答对即清理，不做连续对 2 次毕业）
    - 重做答错 -> 留在待清理列表，计入错误次数
    """

    __tablename__ = "redo_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    quiz_id: Mapped[str] = mapped_column(String(32), index=True)
    question_id: Mapped[str] = mapped_column(String(64))
    selected_answers: Mapped[list[str]] = mapped_column(JSON)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
