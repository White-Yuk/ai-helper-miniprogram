"""向量存储封装测试（add-rag-knowledge-base 任务 4.1）。

使用注入式查表 Fake 嵌入（精确定义向量夹角）+ 临时目录真实 Chroma（本地磁盘）。
覆盖：写入计数 / 相似度查询排序与 metadata / 按 doc_id 删除 / 用户 collection 隔离 / 空 collection。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from langchain_core.embeddings import Embeddings

from app.services.vector_store import VectorStore, collection_name, default_chroma_dir


class FakeEmbeddings(Embeddings):
    """查表优先级最高的确定性假嵌入（未命中时按文本哈希生成稳定向量）。"""

    def __init__(self, table: dict[str, list[float]] | None = None, dim: int = 8):
        self.table = table or {}
        self.dim = dim

    def _hash_vector(self, text: str) -> list[float]:
        digest = hashlib.md5(text.encode("utf-8")).digest()
        return [digest[i % len(digest)] / 255.0 for i in range(self.dim)]

    def _vec(self, text: str) -> list[float]:
        return self.table.get(text, self._hash_vector(text))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


# 精确夹角表：[1,0,0] 与 [0,1,0] 正交
EMBED_TABLE = {
    "RAG 是先检索再生成": [1.0, 0.0, 0.0],
    "今天天气不错": [0.0, 1.0, 0.0],
    "什么是检索增强": [1.0, 0.0, 0.0],
}


@pytest.fixture
def store(tmp_path: Path) -> VectorStore:
    return VectorStore(persist_dir=tmp_path / "chroma", embeddings=FakeEmbeddings(EMBED_TABLE))


class TestCollectionHelpers:
    def test_collection_name(self):
        assert collection_name(1) == "kb_1"
        assert collection_name(42) == "kb_42"


class TestVectorStore:
    def test_add_and_count(self, store: VectorStore):
        written = store.add_chunks(1, "doc_a", "a.pdf", ["RAG 是先检索再生成", "今天天气不错"])
        assert written == 2
        assert store.count(1) == 2

    def test_search_returns_sorted_with_metadata(self, store: VectorStore):
        store.add_chunks(1, "doc_a", "a.pdf", ["RAG 是先检索再生成"])
        store.add_chunks(1, "doc_b", "b.md", ["今天天气不错"])

        results = store.search(1, "什么是检索增强", k=2)
        assert len(results) == 2
        first_doc, first_score = results[0]
        assert first_doc.metadata["filename"] == "a.pdf"
        assert first_doc.metadata["doc_id"] == "doc_a"
        assert first_doc.metadata["chunk_index"] == 0
        assert first_score == pytest.approx(0.0, abs=1e-4)  # 同向 → cosine 距离≈0
        _, second_score = results[1]
        assert second_score == pytest.approx(1.0, abs=1e-4)  # 正交 → 距离≈1

    def test_delete_by_doc(self, store: VectorStore):
        store.add_chunks(1, "doc_a", "a.pdf", ["RAG 是先检索再生成", "今天天气不错"])
        store.add_chunks(1, "doc_b", "b.md", ["RAG 是先检索再生成"])
        assert store.count(1) == 3

        store.delete_by_doc(1, "doc_a")
        assert store.count(1) == 1

        results = store.search(1, "什么是检索增强", k=5)
        assert all(doc.metadata["doc_id"] == "doc_b" for doc, _ in results)

    def test_delete_when_collection_missing(self, store: VectorStore):
        store.delete_by_doc(99, "doc_x")  # 不抛异常

    def test_user_isolation(self, store: VectorStore):
        store.add_chunks(1, "doc_a", "a.pdf", ["RAG 是先检索再生成"])

        # 用户 2 没有数据：查询为空、计数为 0
        assert store.count(2) == 0
        assert store.search(2, "什么是检索增强", k=5) == []

        # 用户 2 写入不影响用户 1
        store.add_chunks(2, "doc_c", "c.md", ["今天天气不错"])
        assert store.count(1) == 1
        assert store.count(2) == 1
        user1_results = store.search(1, "什么是检索增强", k=5)
        assert all(doc.metadata["filename"] == "a.pdf" for doc, _ in user1_results)

    def test_empty_collection_search(self, store: VectorStore):
        assert store.search(7, "任意查询", k=3) == []
        assert store.collection_exists(7) is False

    def test_chunk_index_metadata(self, store: VectorStore):
        store.add_chunks(1, "doc_a", "a.pdf", ["RAG 是先检索再生成", "今天天气不错"])
        results = store.search(1, "什么是检索增强", k=5)
        indexes = sorted(doc.metadata["chunk_index"] for doc, _ in results)
        assert indexes == [0, 1]
