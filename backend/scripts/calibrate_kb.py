"""资料库检索阈值标定脚本（add-rag-knowledge-base 任务 7.2）。

用法（backend 目录）：
    .venv/Scripts/python.exe scripts/calibrate_kb.py

- 选取最近有就绪文档的用户，用真实查询测量 cosine 距离分布；
- 相关查询（应与文档内容相关）↔ 无关查询（应与文档无关）；
- 输出观察记录，辅助确定 `kb_similarity_threshold` 默认值。

说明：真实调用百炼 embedding + 本地 Chroma；不属于 tests/ 单元测试套件。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.db import get_session_factory
from app.models.document import Document
from app.services.vector_store import VectorStore

RELEVANT_QUERIES = [
    "RAG 的关键组件有哪些",
    "什么是检索增强生成",
    "向量数据库的作用",
]
IRRELEVANT_QUERIES = [
    "法国大革命的历史意义",
    "如何做一道番茄炒蛋",
    "Nginx 反向代理配置",
]


def find_user_with_docs() -> int | None:
    """找最近有就绪文档的用户（标定样本）。"""
    session = get_session_factory()()
    try:
        return session.scalars(
            select(Document.user_id)
            .where(Document.status == "ready")
            .order_by(Document.id.desc())
            .limit(1)
        ).first()
    finally:
        session.close()


def main() -> int:
    user_id = find_user_with_docs()
    if user_id is None:
        print("[FAIL] 没有就绪文档的用户（先上传一份文档再标定）")
        return 1
    print(f"使用用户 user_id={user_id} 的资料库进行标定")
    print("=" * 58)

    store = VectorStore()
    print(f"资料库块数：{store.count(user_id)}")

    def run_group(title: str, queries: list[str]) -> list[float]:
        print(f"\n【{title}】")
        bests: list[float] = []
        for query in queries:
            results = store.search(user_id, query, k=5)
            dists = [round(score, 4) for _, score in results]
            best = min(dists) if dists else None
            bests.append(best if best is not None else float("inf"))
            print(f"  {query}")
            print(f"    top5 cosine 距离：{dists if dists else '（无结果）'} → 最近：{best}")
        return bests

    relevant = run_group("相关查询（期望命中：距离低）", RELEVANT_QUERIES)
    irrelevant = run_group("无关查询（期望被阈值过滤：距离高）", IRRELEVANT_QUERIES)

    finite_relevant = [d for d in relevant if d != float("inf")]
    max_relevant = max(finite_relevant) if finite_relevant else float("inf")
    min_irrelevant = min(irrelevant)

    print("\n" + "=" * 58)
    print("观察记录：")
    if finite_relevant:
        print(f"  相关查询最近距离区间：[{min(finite_relevant):.4f}, {max_relevant:.4f}]")
    else:
        print("  相关查询：全部无结果（请检查文档内容与查询语言）")
    print(f"  无关查询最近距离最小值：{min_irrelevant:.4f}")
    if finite_relevant and max_relevant < min_irrelevant:
        margin = (max_relevant + min_irrelevant) / 2
        print(f"  → 两类查询可分：建议阈值取中间值附近 ≈ {margin:.2f}")
    else:
        print("  → 存在重叠：暂保持当前阈值（可在 .env 调整 KB_SIMILARITY_THRESHOLD 后复测）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
