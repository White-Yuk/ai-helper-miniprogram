"""数据层测试：用户模型与默认昵称（TDD 先行）。

运行：.venv/Scripts/pytest tests/test_db_layer.py
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError


class TestUserModel:
    """User 模型：建表、读写、唯一约束。"""

    def test_create_and_query_user(self, db_session):
        from app.models.user import User

        user = User(openid="openid_abc", nickname="小衰学习家0001")
        db_session.add(user)
        db_session.commit()

        loaded = db_session.scalars(select(User).where(User.openid == "openid_abc")).one()
        assert loaded.id is not None
        assert loaded.nickname == "小衰学习家0001"
        assert loaded.avatar == ""
        assert isinstance(loaded.created_at, datetime)
        assert isinstance(loaded.last_login_at, datetime)

    def test_openid_unique(self, db_session):
        from app.models.user import User

        db_session.add(User(openid="dup_openid"))
        db_session.commit()

        db_session.add(User(openid="dup_openid"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_defaults(self, db_session):
        """昵称/头像未指定时为空串（默认昵称由登录服务生成，模型层不掺业务）。"""
        from app.models.user import User

        user = User(openid="openid_defaults")
        db_session.add(user)
        db_session.commit()

        assert user.nickname == ""
        assert user.avatar == ""


class TestDefaultNickname:
    """默认昵称：基于 openid 稳定派生（同一用户每次一致）。"""

    def test_stable_for_same_openid(self):
        from app.utils.nickname import build_default_nickname

        assert build_default_nickname("oX1a2b3c") == build_default_nickname("oX1a2b3c")

    def test_prefix_and_number_format(self):
        from app.utils.nickname import build_default_nickname

        name = build_default_nickname("oX1a2b3c")
        assert name.startswith("小衰学习家")
        suffix = name[len("小衰学习家"):]
        assert len(suffix) == 4 and suffix.isdigit()

    def test_different_openids_get_different_names(self):
        from app.utils.nickname import build_default_nickname

        assert build_default_nickname("openid_aaa") != build_default_nickname("openid_bbb")
