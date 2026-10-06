"""文档接口测试（add-rag-knowledge-base 任务 4.3）。

环境：SQLite 临时库（client_db）+ 临时上传目录 + 假嵌入向量库 + 禁用真实线程池。
覆盖：上传受理 / 未登录 4003 / 格式与大小拒绝 4000 / 未启用拒绝 / 列表隔离 / 删除 / 越权 404。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.conftest import login_headers, login_user

pytestmark = pytest.mark.usefixtures("auth_settings")

UPLOAD_TEXT = "检索增强生成的核心流程是先检索相关资料，再让大模型生成回答。" * 5


@pytest.fixture()
def kb_env(tmp_path, monkeypatch, client_db):
    """隔离外部依赖：上传目录 / 向量库 / 提交函数（禁止真实线程）。"""
    from app.services import doc_service
    from app.services.vector_store import VectorStore
    from tests.test_vector_store import FakeEmbeddings

    settings = SimpleNamespace(
        upload_dir=str(tmp_path / "uploads"),
        dashscope_api_key="sk-test",
        upload_max_size_mb=20,
        doc_worker_concurrency=1,
        kb_chunk_size=80,
        kb_chunk_overlap=10,
    )
    monkeypatch.setattr("app.services.doc_service.get_settings", lambda: settings)
    monkeypatch.setattr("app.utils.text_splitter.get_settings", lambda: settings)
    monkeypatch.setattr(doc_service, "submit_document", lambda doc_id: None)
    store = VectorStore(persist_dir=tmp_path / "chroma", embeddings=FakeEmbeddings())
    monkeypatch.setattr(doc_service, "get_vector_store", lambda: store)

    return SimpleNamespace(client=client_db, store=store, settings=settings, tmp=tmp_path)


def _upload(client, headers, filename: str = "笔记.md", content: bytes | None = None):
    content = content if content is not None else UPLOAD_TEXT.encode("utf-8")
    return client.post(
        "/api/v1/documents",
        files={"file": (filename, content, "application/octet-stream")},
        headers=headers,
    )


class TestUploadDocument:
    def test_upload_accepted(self, kb_env):
        headers, user_id = login_user(kb_env.client, "device_upload")
        resp = _upload(kb_env.client, headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0
        doc_id = body["data"]["doc_id"]
        assert doc_id.startswith("doc_")
        assert body["data"]["status"] == "pending"

        # 原文件已落盘（存储名用 doc_id）
        path = Path(kb_env.settings.upload_dir) / str(user_id) / f"{doc_id}.md"
        assert path.exists()

    def test_upload_requires_login(self, kb_env):
        resp = kb_env.client.post(
            "/api/v1/documents",
            files={"file": ("a.md", b"x" * 30, "application/octet-stream")},
        )
        assert resp.status_code == 401
        assert resp.json()["code"] == 4003

    def test_upload_rejects_unsupported_type(self, kb_env):
        headers, _ = login_user(kb_env.client, "device_type")
        resp = _upload(kb_env.client, headers, filename="a.txt", content=b"x" * 30)
        assert resp.status_code == 422
        assert resp.json()["code"] == 4000
        assert "仅支持" in resp.json()["message"]

    def test_upload_rejects_too_large(self, kb_env):
        headers, _ = login_user(kb_env.client, "device_big")
        big = b"x" * (20 * 1024 * 1024 + 1)
        resp = _upload(kb_env.client, headers, filename="big.md", content=big)
        assert resp.status_code == 422
        assert "20MB" in resp.json()["message"]

    def test_upload_disabled_without_key(self, kb_env, monkeypatch):
        headers, _ = login_user(kb_env.client, "device_nokey")
        monkeypatch.setattr(
            "app.services.doc_service.get_settings",
            lambda: SimpleNamespace(dashscope_api_key="", upload_max_size_mb=20),
        )
        resp = _upload(kb_env.client, headers)
        assert resp.status_code == 422
        assert "未启用" in resp.json()["message"]


class TestListDocuments:
    def test_list_returns_own_documents(self, kb_env):
        headers_a, _ = login_user(kb_env.client, "device_list_a")
        headers_b, _ = login_user(kb_env.client, "device_list_b")

        resp = _upload(kb_env.client, headers_a)
        doc_id = resp.json()["data"]["doc_id"]

        # B 的列表为空（隔离）
        resp_b = kb_env.client.get("/api/v1/documents", headers=headers_b)
        assert resp_b.json()["data"]["documents"] == []

        # A 的列表含上传的文档与完整字段
        resp_a = kb_env.client.get("/api/v1/documents", headers=headers_a)
        documents = resp_a.json()["data"]["documents"]
        assert len(documents) == 1
        assert documents[0]["doc_id"] == doc_id
        assert documents[0]["filename"] == "笔记.md"
        assert documents[0]["status"] == "pending"
        assert documents[0]["steps"] == []
        assert documents[0]["created_at"]


class TestDeleteDocument:
    def test_delete_removes_from_list(self, kb_env):
        headers, _ = login_user(kb_env.client, "device_del")
        doc_id = _upload(kb_env.client, headers).json()["data"]["doc_id"]

        resp = kb_env.client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == {"doc_id": doc_id, "deleted": True}

        listed = kb_env.client.get("/api/v1/documents", headers=headers).json()["data"]["documents"]
        assert listed == []

    def test_delete_other_user_404(self, kb_env):
        headers_a, _ = login_user(kb_env.client, "device_del_a")
        headers_b, _ = login_user(kb_env.client, "device_del_b")
        doc_id = _upload(kb_env.client, headers_a).json()["data"]["doc_id"]

        resp = kb_env.client.delete(f"/api/v1/documents/{doc_id}", headers=headers_b)
        assert resp.status_code == 404
        assert resp.json()["code"] == 4005

        # A 的文档仍在
        listed = kb_env.client.get("/api/v1/documents", headers=headers_a).json()["data"]["documents"]
        assert len(listed) == 1

    def test_delete_missing_404(self, kb_env):
        headers, _ = login_user(kb_env.client, "device_del_missing")
        resp = kb_env.client.delete("/api/v1/documents/doc_not_exist", headers=headers)
        assert resp.status_code == 404
        assert resp.json()["code"] == 4005


class TestUnauthorized:
    def test_list_requires_login(self, kb_env):
        resp = kb_env.client.get("/api/v1/documents")
        assert resp.status_code == 401
        assert resp.json()["code"] == 4003
