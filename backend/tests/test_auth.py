"""登录与鉴权接口测试（TDD 先行）。

覆盖：
- JWT 编解码（security 单元）
- 开发态模拟登录 /auth/dev-login
- 真实微信登录 /auth/login（code2Session 通过依赖注入 mock，不触碰真实网络）
- 鉴权依赖与 /me 接口

说明：测试通过环境变量隔离配置，不依赖 backend/.env 的实际内容。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _isolate_settings(monkeypatch):
    """隔离登录相关配置（不读 .env 的真实值），并在测试后清理缓存。"""
    monkeypatch.setenv("AUTH_MOCK_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-pytest-0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("JWT_EXPIRE_DAYS", "30")
    monkeypatch.setenv("WECHAT_APPID", "")
    monkeypatch.setenv("WECHAT_SECRET", "")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _dev_login(client, device_id: str = "device_001") -> dict:
    """辅助：调用 dev-login 并返回 data。"""
    resp = client.post("/api/v1/auth/dev-login", json={"device_id": device_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    return body["data"]


class TestTokenSecurity:
    """JWT 工具：签发 / 解析 / 防篡改 / 过期。"""

    def test_create_and_decode_roundtrip(self):
        from app.core.security import create_access_token, decode_token

        token, expires_at = create_access_token(42)
        assert isinstance(token, str) and token
        assert expires_at > datetime.now(timezone.utc)
        assert decode_token(token) == 42

    def test_tampered_token_rejected(self):
        import jwt

        from app.core.security import create_access_token, decode_token

        token, _ = create_access_token(1)
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(token + "x")

    def test_expired_token_rejected(self):
        import jwt

        from app.core.security import decode_token

        expired = jwt.encode(
            {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            "test-secret-for-pytest-0123456789abcdef0123456789abcdef",
            algorithm="HS256",
        )
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(expired)


class TestDevLogin:
    """开发态模拟登录。"""

    def test_creates_user_and_returns_token(self, client_db, db_session):
        from app.models.user import User

        data = _dev_login(client_db, "device_001")

        assert data["is_new"] is True
        assert data["token"]
        assert data["user"]["nickname"].startswith("小衰学习家")
        assert data["user"]["avatar"] == ""

        users = db_session.scalars(select(User)).all()
        assert len(users) == 1
        assert users[0].openid.startswith("mock_")

    def test_same_device_reuses_user(self, client_db, db_session):
        from app.models.user import User

        first = _dev_login(client_db, "device_001")
        second = _dev_login(client_db, "device_001")

        assert second["is_new"] is False
        assert second["user"]["id"] == first["user"]["id"]
        assert len(db_session.scalars(select(User)).all()) == 1

    def test_different_devices_get_different_users(self, client_db):
        first = _dev_login(client_db, "device_001")
        second = _dev_login(client_db, "device_002")
        assert first["user"]["id"] != second["user"]["id"]

    def test_device_id_required(self, client_db):
        resp = client_db.post("/api/v1/auth/dev-login", json={"device_id": ""})
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000

    def test_returns_404_when_mock_disabled(self, client_db, monkeypatch):
        from app.core.config import get_settings

        monkeypatch.setenv("AUTH_MOCK_ENABLED", "false")
        get_settings.cache_clear()

        resp = client_db.post("/api/v1/auth/dev-login", json={"device_id": "device_001"})
        assert resp.status_code == 404
        assert resp.json()["code"] == 4005


class TestWechatLogin:
    """真实微信登录（code2Session 走依赖覆盖，不触网）。"""

    @staticmethod
    def _override_code2session(client, fake):
        from app.api.v1.routes.auth import get_code2session

        client.app.dependency_overrides[get_code2session] = lambda: fake

    def test_login_success_creates_user(self, client_db, db_session):
        from app.models.user import User

        def fake_code2session(code: str) -> str:
            assert code == "ok_code"
            return "openid_from_wx"

        self._override_code2session(client_db, fake_code2session)

        resp = client_db.post("/api/v1/auth/login", json={"code": "ok_code"})
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["is_new"] is True
        assert data["token"]
        assert data["user"]["nickname"].startswith("小衰学习家")

        user = db_session.scalars(select(User)).one()
        assert user.openid == "openid_from_wx"

    def test_login_invalid_code_rejected(self, client_db):
        from app.services.wechat_client import WechatCode2SessionError

        def fake_code2session(code: str) -> str:
            raise WechatCode2SessionError("invalid code")

        self._override_code2session(client_db, fake_code2session)

        resp = client_db.post("/api/v1/auth/login", json={"code": "bad_code"})
        assert resp.status_code == 400
        assert resp.json()["code"] == 4004

    def test_login_without_appid_config_returns_4004(self, client_db):
        """未配置 AppID/AppSecret 时，真实登录直接返回友好错误（不触网）。"""
        resp = client_db.post("/api/v1/auth/login", json={"code": "whatever"})
        assert resp.status_code == 400
        assert resp.json()["code"] == 4004

    def test_code_required(self, client_db):
        resp = client_db.post("/api/v1/auth/login", json={"code": ""})
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000


class TestMeEndpoint:
    """鉴权依赖 + 用户信息接口。"""

    def test_requires_token(self, client_db):
        resp = client_db.get("/api/v1/me")
        assert resp.status_code == 401
        assert resp.json()["code"] == 4003

    def test_invalid_token_rejected(self, client_db):
        resp = client_db.get("/api/v1/me", headers={"Authorization": "Bearer not-a-token"})
        assert resp.status_code == 401
        assert resp.json()["code"] == 4003

    def test_expired_token_rejected(self, client_db):
        import jwt

        expired = jwt.encode(
            {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            "test-secret-for-pytest-0123456789abcdef0123456789abcdef",
            algorithm="HS256",
        )
        resp = client_db.get("/api/v1/me", headers={"Authorization": f"Bearer {expired}"})
        assert resp.status_code == 401
        assert resp.json()["code"] == 4003

    def test_returns_current_user(self, client_db):
        data = _dev_login(client_db, "device_me")

        resp = client_db.get("/api/v1/me", headers={"Authorization": f"Bearer {data['token']}"})
        assert resp.status_code == 200, resp.text
        me = resp.json()["data"]
        assert me["id"] == data["user"]["id"]
        assert me["nickname"] == data["user"]["nickname"]
        assert me["avatar"] == ""
