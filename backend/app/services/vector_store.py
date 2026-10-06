"""向量存储封装：langchain-chroma（每用户一个 collection，cosine 空间）。

对齐 design.md D2：
- 持久化到配置目录（默认 backend/data/chroma；chromadb 的同一路径 PersistentClient
  在进程内共享，天然单例）；
- 每用户 collection `kb_{user_id}`（物理隔离）；collection 内 metadata 区分文档与块
  （doc_id / filename / chunk_index）；
- cosine 空间：查询 score = 1 - 余弦相似度（T2 冒烟实测，scripts/check_chroma_smoke.py）；
- 只写入处理成功（ready）文档的向量（由调用方 doc_service 保证）。
"""
from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.core.config import get_settings


def default_chroma_dir() -> Path:
    """向量库目录（配置为空时 = backend/data/chroma）。"""
    settings = get_settings()
    if settings.chroma_dir:
        return Path(settings.chroma_dir)
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / "data" / "chroma"


def collection_name(user_id: int) -> str:
    """用户 collection 名（隔离边界）。"""
    return f"kb_{user_id}"


class VectorStore:
    """用户资料库的向量读写封装（一个实例对应一个持久化目录）。"""

    def __init__(self, persist_dir: Path | None = None, embeddings=None):
        """em：embeddings 可注入（测试用 Fake）；未注入时延迟从配置构建。"""
        self._persist_dir = Path(persist_dir) if persist_dir else default_chroma_dir()
        self._embeddings = embeddings

    def _embeddings_or_build(self):
        if self._embeddings is None:
            from app.llm.embedding import build_embeddings

            self._embeddings = build_embeddings()
        return self._embeddings

    def _open(self, user_id: int) -> Chroma:
        return Chroma(
            collection_name=collection_name(user_id),
            embedding_function=self._embeddings_or_build(),
            persist_directory=str(self._persist_dir),
            collection_metadata={"hnsw:space": "cosine"},
        )

    def collection_exists(self, user_id: int) -> bool:
        """collection 是否已创建（未上传过文档的用户不存在）。"""
        from chromadb import PersistentClient

        client = PersistentClient(path=str(self._persist_dir))
        return any(c.name == collection_name(user_id) for c in client.list_collections())

    def add_chunks(self, user_id: int, doc_id: str, filename: str, chunks: list[str]) -> int:
        """写入一个文档的全部分块（向量由 embedding 组件计算），返回写入块数。"""
        if not chunks:
            return 0
        store = self._open(user_id)
        documents = [
            Document(
                page_content=chunk,
                metadata={"doc_id": doc_id, "filename": filename, "chunk_index": index},
            )
            for index, chunk in enumerate(chunks)
        ]
        ids = [f"{doc_id}:{index}" for index in range(len(chunks))]
        store.add_documents(documents, ids=ids)
        return len(chunks)

    def delete_by_doc(self, user_id: int, doc_id: str) -> None:
        """删除一个文档的全部向量（collection 不存在时静默跳过）。"""
        if not self.collection_exists(user_id):
            return
        store = self._open(user_id)
        store.delete(where={"doc_id": doc_id})

    def search(self, user_id: int, query: str, k: int = 5) -> list[tuple[Document, float]]:
        """相似度查询：返回 [(Document, cosine 距离)]；collection 不存在 → 空列表。"""
        if not self.collection_exists(user_id):
            return []
        store = self._open(user_id)
        return store.similarity_search_with_score(query, k=k)

    def count(self, user_id: int) -> int:
        """用户 collection 的向量总数（collection 不存在 → 0）。"""
        if not self.collection_exists(user_id):
            return 0
        store = self._open(user_id)
        return store._collection.count()
