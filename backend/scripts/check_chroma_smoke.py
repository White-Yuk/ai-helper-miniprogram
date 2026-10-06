"""前置验证 T2：Chromadb + langchain-chroma 冒烟（Python 3.14 / Windows）。

验证内容（对齐 add-rag-knowledge-base tasks 1.3 / design D2）：
    [1] 创建带 cosine 空间的持久化 collection（模拟每用户 `kb_{user_id}`）
    [2] 写入自定义嵌入（lookup 假嵌入——精确定义向量夹角，验证距离语义）
    [3] `similarity_search_with_score` 查询：确认距离语义（cosine 距离 = 1 - 余弦相似度）
    [4] 按 where（doc_id）删除
    [5] 重启进程（subprocess 新进程）后：剩余数据仍可查、已删数据不可见

用法（backend 目录）：
    .venv/Scripts/python.exe scripts/check_chroma_smoke.py

说明：完全离线（lookup 假嵌入，不触网、不消耗额度）；不属于 tests/ 单元测试套件。
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

# 精确控制夹角的查询表：
#   docA 与 query 同向（cos=1 → 距离≈0）；docB 与 query 正交（cos=0 → 距离≈1）
EMBED_TABLE: dict[str, list[float]] = {
    "docA：RAG 是先检索再生成": [1.0, 0.0, 0.0],
    "docB：今天天气不错": [0.0, 1.0, 0.0],
    "查询：RAG 流程是什么": [1.0, 0.0, 0.0],
    "持久化验证查询：天气": [0.0, 1.0, 0.0],
}


class LookupEmbeddings(Embeddings):
    """按查表返回预置向量的假嵌入（测试专用，精确定义夹角）。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [EMBED_TABLE[t] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return EMBED_TABLE[text]


COLLECTION = "kb_1"


def open_store(persist_dir: str) -> Chroma:
    return Chroma(
        collection_name=COLLECTION,
        embedding_function=LookupEmbeddings(),
        persist_directory=persist_dir,
        collection_metadata={"hnsw:space": "cosine"},
    )


def verify_persist(persist_dir: str) -> int:
    """子进程模式：新进程打开同一目录，验证持久化与删除效果。"""
    print("--- [5] 子进程（模拟重启）持久化验证 ---")
    store = open_store(persist_dir)
    count = store._collection.count()
    print(f"    新进程打开 collection：文档块数 = {count}（期望 1：docB）")

    results = store.similarity_search_with_score("持久化验证查询：天气", k=5)
    hit_files = [doc.metadata.get("filename") for doc, _ in results]
    print(f"    查询 docB 命中：{hit_files}")

    gone = store.similarity_search_with_score("查询：RAG 流程是什么", k=5)
    gone_files = [doc.metadata.get("filename") for doc, _ in gone]
    print(f"    查询已删除的 docA：命中文档 = {gone_files}（不得包含 a.pdf）")

    ok = count == 1 and hit_files == ["b.md"] and "a.pdf" not in gone_files
    print(f"    {'✓ 持久化+删除均验证通过' if ok else '✗ 验证未通过'}")
    return 0 if ok else 1


def main(verify_dir: str | None = None) -> int:
    if verify_dir:
        return verify_persist(verify_dir)

    print("=" * 56)
    print("T2 冒烟：langchain-chroma（cosine 空间 / 持久化 / 删除）")
    print("=" * 56)

    persist_dir = tempfile.mkdtemp(prefix="chroma_smoke_")
    print(f"[0] 临时持久化目录：{persist_dir}")

    store = open_store(persist_dir)
    print(f"[1] 创建 collection `{COLLECTION}`（hnsw:space=cosine）OK")

    store.add_texts(
        ["docA：RAG 是先检索再生成", "docB：今天天气不错"],
        metadatas=[
            {"doc_id": "d1", "filename": "a.pdf", "chunk_index": 0},
            {"doc_id": "d2", "filename": "b.md", "chunk_index": 0},
        ],
        ids=["d1:0", "d2:0"],
    )
    print(f"[2] 写入 2 个块 OK（collection 计数 = {store._collection.count()}）")

    results = store.similarity_search_with_score("查询：RAG 流程是什么", k=2)
    print("[3] similarity_search_with_score 结果（distance 语义验证）：")
    distances = []
    for doc, score in results:
        distances.append(score)
        print(f"    - {doc.metadata['filename']} | distance={score:.4f} | {doc.page_content[:18]}…")
    same_dir, ortho = distances[0], distances[1]
    semantic_ok = abs(same_dir) < 1e-4 and abs(ortho - 1.0) < 1e-4
    print(f"    语义断言：同向距离≈0（实际 {same_dir:.6f}）、正交距离≈1（实际 {ortho:.6f}）→ {'✓ 距离 = 1 - 余弦相似度' if semantic_ok else '✗ 与预期不符，需记录实际语义'}")

    try:
        store.delete(filter={"doc_id": "d1"})
        delete_style = "filter="
    except TypeError:
        store.delete(where={"doc_id": "d1"})
        delete_style = "where="
    remaining = store._collection.count()
    print(f"[4] 按 doc_id 删除 docA OK（delete({delete_style}...)；剩余计数 = {remaining}，期望 1）")

    # 子进程验证重启持久化（PYTHONIOENCODING 确保中文输出不乱码）
    import os

    proc = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--verify-persist", persist_dir],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    print(proc.stdout, end="")
    if proc.stderr.strip():
        print("    子进程 stderr：", proc.stderr.strip()[:800])

    all_ok = semantic_ok and remaining == 1 and proc.returncode == 0
    print("-" * 56)
    print("结论：T2 " + ("通过（cosine 空间 / 距离语义 / 删除 / 持久化 全部验证）" if all_ok else "存在未通过项，见上方输出"))

    # 清理临时目录
    import shutil

    shutil.rmtree(persist_dir, ignore_errors=True)
    print(f"     已清理临时目录：{persist_dir}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--verify-persist":
        raise SystemExit(verify_persist(sys.argv[2]))
    raise SystemExit(main())
