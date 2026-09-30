"""数据库基础设施：引擎、会话、ORM 基类与 FastAPI 依赖。"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """全部 ORM 模型的基类。"""


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """进程内单例引擎（延迟创建，便于测试与配置加载顺序调整）。"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_settings().db_url,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级数据库会话（事务由服务层显式提交）。"""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """创建全部数据表（开发/测试用；不处理版本迁移）。"""
    import app.models.user  # noqa: F401  确保模型注册到 Base.metadata

    Base.metadata.create_all(bind=get_engine())
