"""文档服务测试（add-rag-knowledge-base 任务 4.2）。

环境：SQLite 临时库 + Fake 嵌入（查表/哈希）+ 临时 Chroma 目录 + tmp 上传目录（全离线）。
覆盖：上传校验 / 落盘与记录 / 处理流水线（成功 / 解析失败 / 向量化失败）/ 步骤内容 /
     删除清理（记录 + 向量 + 文件）/ 处理中删除竞态（写后补偿清理）/ 启动兜底。
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.exceptions import BizException
from app.models.document import Document
from app.services import doc_service
from app.services.vector_store import VectorStore
from tests.test_vector_store import FakeEmbeddings

LONG_TEXT = "检索增强生成的核心流程是先检索相关资料，再让大模型生成回答。" * 5


class _NoopExecutor:
    """占位线程池：submit 不执行（测试直接同步调用 _process_document）。"""

    def submit(self, fn, *args, **kwargs):  # noqa: ANN001
        return None


@pytest.fixture()
def doc_env(tmp_path, monkeypatch):
    """隔离环境：SQLite + 假嵌入 + 临时目录；patch doc_service 的全部外部依赖。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401
    from app.core.db import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'doc.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

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
    monkeypatch.setattr("app.services.doc_service.get_session_factory", lambda: factory)
    monkeypatch.setattr("app.services.doc_service._get_executor", lambda: _NoopExecutor())

    store = VectorStore(persist_dir=tmp_path / "chroma", embeddings=FakeEmbeddings())
    monkeypatch.setattr("app.services.doc_service.get_vector_store", lambda: store)

    yield SimpleNamespace(
        engine=engine, session_factory=factory, store=store, settings=settings, tmp=tmp_path
    )
    engine.dispose()


def _create_doc(doc_env, user_id: int = 1, filename: str = "notes.md", content: bytes | None = None) -> str:
    """辅助：落盘并创建文档记录，返回 doc_id。"""
    content = content if content is not None else LONG_TEXT.encode("utf-8")
    session = doc_env.session_factory()
    try:
        document = doc_service.save_upload(session, user_id=user_id, filename=filename, content=content)
        return document.doc_id
    finally:
        session.close()


def _load_doc(doc_env, doc_id: str) -> Document | None:
    session = doc_env.session_factory()
    try:
        return session.query(Document).filter_by(doc_id=doc_id).one_or_none()
    finally:
        session.close()


class TestValidateUpload:
    def test_ok(self, doc_env):
        assert doc_service.validate_upload("笔记.md", b"x" * 10) == "md"
        assert doc_service.validate_upload("doc.PDF", b"x" * 10) == "pdf"

    def test_unsupported_type(self, doc_env):
        with pytest.raises(BizException) as exc_info:
            doc_service.validate_upload("notes.txt", b"x" * 10)
        assert exc_info.value.code == 4000

    def test_empty_content(self, doc_env):
        with pytest.raises(BizException) as exc_info:
            doc_service.validate_upload("notes.md", b"")
        assert exc_info.value.code == 4000

    def test_too_large(self, doc_env):
        big = b"x" * (20 * 1024 * 1024 + 1)
        with pytest.raises(BizException) as exc_info:
            doc_service.validate_upload("notes.md", big)
        assert "20MB" in exc_info.value.message

    def test_disabled_without_key(self, doc_env, monkeypatch):
        monkeypatch.setattr(
            "app.services.doc_service.get_settings",
            lambda: SimpleNamespace(dashscope_api_key="", upload_max_size_mb=20),
        )
        with pytest.raises(BizException) as exc_info:
            doc_service.validate_upload("notes.md", b"x" * 10)
        assert "未启用" in exc_info.value.message


class TestSaveUpload:
    def test_saves_file_and_record(self, doc_env):
        content = LONG_TEXT.encode("utf-8")
        doc_id = _create_doc(doc_env, filename="我的笔记.md", content=content)

        path = Path(doc_env.settings.upload_dir) / "1" / f"{doc_id}.md"
        assert path.exists()
        assert path.read_bytes() == content

        document = _load_doc(doc_env, doc_id)
        assert document is not None
        assert document.status == "pending"
        assert document.file_type == "md"
        assert document.file_size == len(content)
        assert document.filename == "我的笔记.md"

    def test_doc_id_format(self, doc_env):
        doc_id = _create_doc(doc_env)
        assert doc_id.startswith("doc_")
        assert len(doc_id) == len("doc_") + 12


class TestProcessDocument:
    def test_pipeline_success(self, doc_env):
        doc_id = _create_doc(doc_env)
        doc_service._process_document(doc_id)

        document = _load_doc(doc_env, doc_id)
        assert document.status == "ready"
        assert document.chunk_count and document.chunk_count >= 1
        assert document.char_count and document.char_count > 0
        assert document.finished_at is not None

        steps = {step["key"]: step for step in document.steps}
        assert {"parse", "split", "embed", "finish"} <= set(steps)
        assert all(step["state"] == "done" for step in document.steps)
        assert f"共 {document.chunk_count} 块" in steps["split"]["detail"]

        # 向量已入库且与分块数一致
        assert doc_env.store.count(1) == document.chunk_count

    def test_parse_failure_marks_failed(self, doc_env):
        doc_id = _create_doc(doc_env, content="太短".encode("utf-8"))
        doc_service._process_document(doc_id)

        document = _load_doc(doc_env, doc_id)
        assert document.status == "failed"
        assert "未提取到有效文本" in document.error_message
        assert doc_env.store.count(1) == 0

    def test_embedding_failure_marks_failed(self, doc_env, monkeypatch):
        doc_id = _create_doc(doc_env)

        class BrokenStore:
            def add_chunks(self, *args, **kwargs):  # noqa: ANN002, ANN003
                raise RuntimeError("embedding service down")

            def delete_by_doc(self, *args, **kwargs):  # noqa: ANN002, ANN003
                pass

        monkeypatch.setattr("app.services.doc_service.get_vector_store", lambda: BrokenStore())
        doc_service._process_document(doc_id)

        document = _load_doc(doc_env, doc_id)
        assert document.status == "failed"
        assert "向量化失败" in document.error_message

    def test_deleted_after_add_compensates(self, doc_env):
        """写入向量期间记录被删除 → 补偿清理刚写入的向量，不更新状态。"""
        doc_id = _create_doc(doc_env)
        store = doc_env.store
        original_add = store.add_chunks

        def add_then_delete(user_id, doc, filename, chunks):
            result = original_add(user_id, doc, filename, chunks)
            # 模拟并发删除：add 完成之后记录被删除
            session = doc_env.session_factory()
            try:
                record = session.query(Document).filter_by(doc_id=doc).one_or_none()
                if record is not None:
                    session.delete(record)
                    session.commit()
            finally:
                session.close()
            return result

        store.add_chunks = add_then_delete
        doc_service._process_document(doc_id)

        assert _load_doc(doc_env, doc_id) is None
        assert store.count(1) == 0  # 补偿清理生效

    def test_missing_document_skips(self, doc_env):
        doc_service._process_document("doc_not_exist")  # 不抛异常


class TestDeleteDocument:
    def test_delete_cleans_record_vector_file(self, doc_env):
        doc_id = _create_doc(doc_env)
        doc_service._process_document(doc_id)
        assert doc_env.store.count(1) > 0
        file_path = Path(doc_env.settings.upload_dir) / "1" / f"{doc_id}.md"
        assert file_path.exists()

        session = doc_env.session_factory()
        try:
            result = doc_service.delete_document(session, user_id=1, doc_id=doc_id)
        finally:
            session.close()

        assert result == {"doc_id": doc_id, "deleted": True}
        assert _load_doc(doc_env, doc_id) is None
        assert doc_env.store.count(1) == 0
        assert not file_path.exists()

    def test_delete_other_user_404(self, doc_env):
        doc_id = _create_doc(doc_env, user_id=1)
        session = doc_env.session_factory()
        try:
            with pytest.raises(BizException) as exc_info:
                doc_service.delete_document(session, user_id=2, doc_id=doc_id)
            assert exc_info.value.code == 4005
        finally:
            session.close()

    def test_delete_pending_document(self, doc_env):
        """任意状态可删（pending 未处理）。"""
        doc_id = _create_doc(doc_env)
        session = doc_env.session_factory()
        try:
            doc_service.delete_document(session, user_id=1, doc_id=doc_id)
        finally:
            session.close()
        assert _load_doc(doc_env, doc_id) is None


class TestListAndGet:
    def test_list_orders_newest_first(self, doc_env):
        first = _create_doc(doc_env, filename="a.md")
        second = _create_doc(doc_env, filename="b.md")
        session = doc_env.session_factory()
        try:
            documents = doc_service.list_documents(session, user_id=1)
            assert [d.doc_id for d in documents] == [second, first]
        finally:
            session.close()

    def test_list_isolated_by_user(self, doc_env):
        mine = _create_doc(doc_env, user_id=1)
        _create_doc(doc_env, user_id=2)
        session = doc_env.session_factory()
        try:
            documents = doc_service.list_documents(session, user_id=1)
            assert [d.doc_id for d in documents] == [mine]
        finally:
            session.close()

    def test_get_other_user_404(self, doc_env):
        doc_id = _create_doc(doc_env, user_id=1)
        session = doc_env.session_factory()
        try:
            with pytest.raises(BizException) as exc_info:
                doc_service.get_user_document(session, user_id=2, doc_id=doc_id)
            assert exc_info.value.code == 4005
        finally:
            session.close()


class TestStaleCleanup:
    def test_mark_stale_failed(self, doc_env):
        pending_id = _create_doc(doc_env)
        count = doc_service.mark_stale_documents_failed()
        assert count == 1

        document = _load_doc(doc_env, pending_id)
        assert document.status == "failed"
        assert document.error_message == "处理中断，请重新上传"

    def test_no_stale_returns_zero(self, doc_env):
        doc_id = _create_doc(doc_env)
        doc_service._process_document(doc_id)
        assert doc_service.mark_stale_documents_failed() == 0
