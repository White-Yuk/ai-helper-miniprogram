"""生成任务 ORM（异步任务 + 轮询）：任务状态 / 步骤 / 结果持久化。

对齐 design.md D4：
- 任务创建即持久化（服务重启后已存在任务仍可查询）；
- steps / request / result 使用 JSON 列（MySQL JSON / SQLite JSON 均兼容）；
- 残留 pending / running 任务由服务启动时兜底标记为 failed。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class GenerationTask(Base):
    """题库生成任务：一次「创建 → 后台执行 → 轮询」对应一条记录。"""

    __tablename__ = "generation_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 任务号（随机生成，即访问凭证）：task_xxxxxxxxxxxx
    task_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    # 可空：匿名任务为 NULL；登录任务归属用户
    user_id: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    # pending / running / done / failed
    status: Mapped[str] = mapped_column(String(8), default="pending", index=True)
    # 请求快照（user_input / question_count / difficulty / question_types）
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    # 步骤列表：[{key, label, detail, state(doing/done), ts}]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # 成功结果（题库数据 + sources + agent_trace）；失败时为 None
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    error_code: Mapped[int | None] = mapped_column(Integer, default=None)
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
