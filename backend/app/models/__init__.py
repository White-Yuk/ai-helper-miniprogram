"""ORM 模型统一注册：导入本包即把所有模型注册到 Base.metadata（建表 / 测试依赖）。"""
from app.models.records import Answer, Quiz, RedoRecord, Report  # noqa: F401
from app.models.user import User  # noqa: F401
