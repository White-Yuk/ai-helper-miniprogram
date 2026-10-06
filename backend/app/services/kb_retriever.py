"""资料库检索器：用户 collection → 相似度查询 → 阈值过滤 → KbHit 列表。

对齐 design.md D5：
- 距离语义 = cosine 距离（1 - 余弦相似度，T2 冒烟实测，scripts/check_chroma_smoke.py）；
- 阈值 kb_similarity_threshold（默认 0.45，保守初值，上线前实测标定）；
- collection 不存在 / 无命中 / 全部低于阈值 → 空列表（不返回噪声）。
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass
class KbHit:
    """单条检索命中：片段文本 / 所属文档名 / 文档号 / cosine 距离。"""

    text: str
    filename: str
    doc_id: str
    distance: float


def get_vector_store():
    """向量库实例（测试可 patch 本函数注入 Fake 嵌入 / 临时目录）。"""
    from app.services.vector_store import VectorStore

    return VectorStore()


def search_knowledge_base(user_id: int, query: str, top_k: int | None = None) -> list[KbHit]:
    """语义检索当前用户资料库，返回达到相关度要求的命中（按相关度排序）。"""
    settings = get_settings()
    k = top_k or settings.kb_top_k
    threshold = settings.kb_similarity_threshold

    hits: list[KbHit] = []
    for document, distance in get_vector_store().search(user_id, query, k=k):
        if float(distance) > threshold:
            continue
        metadata = document.metadata or {}
        hits.append(
            KbHit(
                text=document.page_content or "",
                filename=str(metadata.get("filename", "")),
                doc_id=str(metadata.get("doc_id", "")),
                distance=float(distance),
            )
        )
    return hits
