"""文档知识库 ORM（RAG 资料库）：用户上传文档的处理状态与结果。

对齐 design.md D2：
- 文档创建即持久化（服务重启后状态仍可查询）；
- steps 使用 JSON 列（与生成任务同格式：key/label/detail/state/ts）；
- 残留 processing 文档由服务启动兜底标记为 failed。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Document(Base):
    """用户上传文档：一次「上传 → 后台处理 → 就绪 / 失败」对应一条记录。"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # 文档号（随机生成，对外标识）：doc_xxxxxxxxxxxx
    doc_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    # 归属用户（上传需登录；索引用于「用户是否有就绪文档」轻查询）
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    # 原始文件名（仅展示；存储文件名使用 doc_id，不信任客户端文件名）
    filename: Mapped[str] = mapped_column(String(255))
    # pdf / docx / md
    file_type: Mapped[str] = mapped_column(String(8))
    file_size: Mapped[int] = mapped_column(Integer)
    # pending / processing / ready / failed
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)
    # 处理步骤：[{key, label, detail, state(doing/done), ts}]
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # 失败原因（可读）
    error_message: Mapped[str | None] = mapped_column(String(500), default=None)
    # 处理结果统计
    chunk_count: Mapped[int | None] = mapped_column(Integer, default=None)
    char_count: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
