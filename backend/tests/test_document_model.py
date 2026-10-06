"""Document 模型 schema 测试（add-rag-knowledge-base 任务 2.3）。"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.document import Document


def _make_doc(doc_id: str = "doc_aaaaaaaaaaaa", **overrides) -> Document:
    defaults = dict(
        doc_id=doc_id,
        user_id=1,
        filename="RAG 入门.pdf",
        file_type="pdf",
        file_size=12345,
    )
    defaults.update(overrides)
    return Document(**defaults)


class TestDocumentModel:
    def test_defaults_and_persistence(self, db_session):
        doc = _make_doc()
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        assert doc.id is not None
        assert doc.status == "pending"
        assert doc.steps == []
        assert doc.error_message is None
        assert doc.chunk_count is None
        assert doc.char_count is None
        assert doc.created_at is not None
        assert doc.updated_at is not None
        assert doc.finished_at is None

    def test_json_steps_roundtrip(self, db_session):
        step = {
            "key": "parse",
            "label": "解析文档",
            "detail": "文本提取完成",
            "state": "done",
            "ts": "2026-10-07T10:00:00",
        }
        doc = _make_doc(doc_id="doc_steps_rt", steps=[step])
        db_session.add(doc)
        db_session.commit()
        db_session.expire_all()  # 强制重新加载，验证 JSON 往返
        got = db_session.get(Document, doc.id)
        assert got.steps == [step]

    def test_status_transitions(self, db_session):
        doc = _make_doc(doc_id="doc_status_1")
        db_session.add(doc)
        db_session.commit()

        doc.status = "processing"
        db_session.commit()
        doc.status = "ready"
        doc.chunk_count = 12
        doc.char_count = 6000
        doc.finished_at = datetime.now()
        db_session.commit()
        db_session.refresh(doc)
        assert doc.status == "ready"
        assert doc.chunk_count == 12
        assert doc.char_count == 6000

    def test_failed_with_error_message(self, db_session):
        doc = _make_doc(doc_id="doc_fail_1", status="failed", error_message="未提取到有效文本")
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)
        assert doc.status == "failed"
        assert doc.error_message == "未提取到有效文本"

    def test_indexes_defined(self):
        """user_id / status / doc_id 均需索引（「用户是否有就绪文档」轻查询依赖）。"""
        index_names = " ".join(str(idx.name) for idx in Document.__table__.indexes)
        assert "doc_id" in index_names
        assert "user_id" in index_names
        assert "status" in index_names

    def test_doc_id_unique(self, db_session):
        db_session.add(_make_doc(doc_id="doc_dup"))
        db_session.commit()
        db_session.add(_make_doc(doc_id="doc_dup"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()
