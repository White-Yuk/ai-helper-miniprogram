"""阶段 7：个人资料接口测试（PUT /me、POST /me/avatar，TDD 先行）。

覆盖：
- 昵称更新与校验（空 / 超长 / 未提供字段）
- 头像 URL 更新
- 头像文件上传：类型白名单、大小限制、落盘（临时目录注入）、未登录
"""
from __future__ import annotations

import pytest

from tests.conftest import login_user

pytestmark = pytest.mark.usefixtures("auth_settings")

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"x" * 256


@pytest.fixture()
def avatar_tmp_dir(tmp_path, app):
    """把头像保存目录重定向到临时目录（不污染仓库 static 目录）。"""
    from app.api.v1.routes.me import get_avatar_dir

    target = tmp_path / "avatars"
    app.dependency_overrides[get_avatar_dir] = lambda: target
    yield target


class TestUpdateProfile:
    def test_requires_login(self, client_db):
        resp = client_db.put("/api/v1/me", json={"nickname": "新名字"})
        assert resp.status_code == 401
        assert resp.json()["code"] == 4003

    def test_update_nickname(self, client_db):
        headers, _ = login_user(client_db, "dev_profile_nick")

        resp = client_db.put("/api/v1/me", json={"nickname": "  RAG 小达人  "}, headers=headers)

        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["nickname"] == "RAG 小达人"  # 自动去首尾空白
        me = client_db.get("/api/v1/me", headers=headers).json()["data"]
        assert me["nickname"] == "RAG 小达人"

    def test_blank_nickname_rejected(self, client_db):
        headers, _ = login_user(client_db, "dev_profile_blank")
        resp = client_db.put("/api/v1/me", json={"nickname": "   "}, headers=headers)
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000

    def test_too_long_nickname_rejected(self, client_db):
        headers, _ = login_user(client_db, "dev_profile_long")
        resp = client_db.put("/api/v1/me", json={"nickname": "名" * 33}, headers=headers)
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000

    def test_no_fields_rejected(self, client_db):
        headers, _ = login_user(client_db, "dev_profile_none")
        resp = client_db.put("/api/v1/me", json={}, headers=headers)
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000

    def test_update_avatar_url(self, client_db):
        headers, _ = login_user(client_db, "dev_profile_avatar")
        resp = client_db.put("/api/v1/me", json={"avatar": "/static/avatars/a1b2.png"}, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["avatar"] == "/static/avatars/a1b2.png"


class TestAvatarUpload:
    def test_requires_login(self, client_db):
        resp = client_db.post(
            "/api/v1/me/avatar",
            files={"file": ("a.png", PNG_BYTES, "image/png")},
        )
        assert resp.status_code == 401

    def test_upload_success_and_saved(self, client_db, avatar_tmp_dir):
        headers, _ = login_user(client_db, "dev_avatar_ok")

        resp = client_db.post(
            "/api/v1/me/avatar",
            files={"file": ("a.png", PNG_BYTES, "image/png")},
            headers=headers,
        )

        assert resp.status_code == 200, resp.text
        url = resp.json()["data"]["url"]
        assert url.startswith("/static/avatars/")
        assert url.endswith(".png")
        saved = avatar_tmp_dir / url.rsplit("/", 1)[-1]
        assert saved.exists()
        assert saved.read_bytes() == PNG_BYTES

    def test_rejects_non_image_type(self, client_db, avatar_tmp_dir):
        headers, _ = login_user(client_db, "dev_avatar_type")
        resp = client_db.post(
            "/api/v1/me/avatar",
            files={"file": ("a.txt", b"hello", "text/plain")},
            headers=headers,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000

    def test_rejects_oversized_file(self, client_db, avatar_tmp_dir):
        headers, _ = login_user(client_db, "dev_avatar_big")
        big = b"x" * (2 * 1024 * 1024 + 1)
        resp = client_db.post(
            "/api/v1/me/avatar",
            files={"file": ("big.png", big, "image/png")},
            headers=headers,
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000

    def test_rejects_empty_file(self, client_db, avatar_tmp_dir):
        headers, _ = login_user(client_db, "dev_avatar_empty")
        resp = client_db.post(
            "/api/v1/me/avatar",
            files={"file": ("a.png", b"", "image/png")},
            headers=headers,
        )
        assert resp.status_code == 422
