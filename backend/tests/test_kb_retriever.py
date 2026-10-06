"""资料库检索器测试（add-rag-knowledge-base 任务 5.1）。

Fake 嵌入（查表控制向量夹角）+ 临时 Chroma；覆盖：命中与阈值过滤 / 排序 / 用户隔离 / 空库 / top_k。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.kb_retriever import search_knowledge_base
from app.services.vector_store import VectorStore
from tests.test_vector_store import FakeEmbeddings

EMBED_TABLE = {
    "RAG 是先检索再生成": [1.0, 0.0, 0.0],
    "今天天气不错": [0.0, 1.0, 0.0],
    "什么是检索增强": [1.0, 0.0, 0.0],
}


@pytest.fixture()
def kb_env(tmp_path, monkeypatch):
    settings = SimpleNamespace(kb_top_k=5, kb_similarity_threshold=0.45)
    monkeypatch.setattr("app.services.kb_retriever.get_settings", lambda: settings)
    store = VectorStore(persist_dir=tmp_path / "chroma", embeddings=FakeEmbeddings(EMBED_TABLE))
    monkeypatch.setattr("app.services.kb_retriever.get_vector_store", lambda: store)
    return SimpleNamespace(store=store, settings=settings)


class TestSearchKnowledgeBase:
    def test_hit_with_threshold_filtering(self, kb_env):
        kb_env.store.add_chunks(1, "doc_a", "a.pdf", ["RAG 是先检索再生成"])
        kb_env.store.add_chunks(1, "doc_b", "b.md", ["今天天气不错"])

        hits = search_knowledge_base(1, "什么是检索增强")
        assert len(hits) == 1  # 无关项（距离≈1）被阈值过滤
        hit = hits[0]
        assert hit.filename == "a.pdf"
        assert hit.doc_id == "doc_a"
        assert hit.distance == pytest.approx(0.0, abs=1e-4)
        assert "RAG" in hit.text

    def test_empty_library_returns_empty(self, kb_env):
        assert search_knowledge_base(1, "任意查询") == []

    def test_user_isolation(self, kb_env):
        kb_env.store.add_chunks(1, "doc_a", "a.pdf", ["RAG 是先检索再生成"])
        assert search_knowledge_base(2, "什么是检索增强") == []

    def test_threshold_relaxed_returns_more_sorted(self, kb_env):
        kb_env.settings.kb_similarity_threshold = 1.5
        kb_env.store.add_chunks(1, "doc_a", "a.pdf", ["RAG 是先检索再生成"])
        kb_env.store.add_chunks(1, "doc_b", "b.md", ["今天天气不错"])

        hits = search_knowledge_base(1, "什么是检索增强")
        assert len(hits) == 2
        assert hits[0].filename == "a.pdf"  # 更相关（距离更小）排前
        assert hits[1].distance > hits[0].distance

    def test_top_k_limit(self, kb_env):
        kb_env.store.add_chunks(
            1, "doc_a", "a.pdf", ["RAG 是先检索再生成", "RAG 是先检索再生成", "RAG 是先检索再生成"]
        )
        hits = search_knowledge_base(1, "什么是检索增强", top_k=2)
        assert len(hits) == 2
