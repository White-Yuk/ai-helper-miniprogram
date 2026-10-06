"""百炼（DashScope）Embedding 连通性检查脚本。

用法（在 backend 目录下执行）：
    .venv/Scripts/python.exe scripts/check_dashscope.py

检查内容（依次执行）：
    [0] .env 中 DASHSCOPE_API_KEY 是否已配置（不输出 Key 内容）
    [1] 单条文本向量化（text-embedding-v4，dimensions=1024）
    [2] 批量文本向量化（3 条，验证批量通道）
    [3] 对照验证：check_embedding_ctx_length=True 的行为（预期失败——验证必须关闭该选项）

说明：真实调用百炼 API，不属于 tests/ 单元测试套件（项目约定：单测不触网）。
输出自动脱敏：异常信息中的 Key 一律打码。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_DIR / ".env"

DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "text-embedding-v4"
DIMENSIONS = 1024


def load_config() -> tuple[str, str]:
    """从 backend/.env 读取 DASHSCOPE_API_KEY 与 BASE_URL（不打印 Key 内容）。"""
    if not ENV_PATH.exists():
        print(f"[FAIL] 未找到 {ENV_PATH}，请先配置 .env")
        return "", ""
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=False)
    key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    base_url = os.getenv("DASHSCOPE_BASE_URL", "").strip() or DEFAULT_BASE_URL
    return key, base_url


def _safe_message(exc: Exception, api_key: str) -> str:
    """异常信息脱敏（防止意外携带 Key），并限制长度。"""
    message = f"{type(exc).__name__}: {exc}"
    if api_key:
        message = message.replace(api_key, "***")
        if len(api_key) > 8:  # 兜底：SDK 报错有时只回显 key 前缀
            message = message.replace(api_key[:8], "***")
    return message[:200]


def build_embeddings(api_key: str, base_url: str, ctx_length_check: bool = False):
    """构建 LangChain OpenAIEmbeddings（与未来出题/资料库链路同一构造方式）。"""
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(
        model=MODEL,
        base_url=base_url,
        api_key=api_key,
        dimensions=DIMENSIONS,
        check_embedding_ctx_length=ctx_length_check,
    )


def main() -> int:
    print("=" * 46)
    print("百炼 Embedding 连通性检查（text-embedding-v4）")
    print("=" * 46)

    api_key, base_url = load_config()
    if not api_key:
        print("[FAIL] .env 中未配置 DASHSCOPE_API_KEY（或为空）")
        print("       获取地址：https://bailian.console.aliyun.com -> API-KEY 管理")
        return 1

    prefix_hint = "是" if api_key.startswith("sk-") else "否（请确认是否复制完整）"
    print(f"[0] Key 已配置（长度 {len(api_key)}，以 sk- 开头：{prefix_hint}）")
    print(f"    base_url：{base_url}")

    ok = True

    # 1) 单条文本
    try:
        embeddings = build_embeddings(api_key, base_url)
        t0 = time.monotonic()
        vec = embeddings.embed_query("RAG 的核心流程是先检索相关资料，再让大模型生成回答")
        elapsed = time.monotonic() - t0
        head = [round(x, 4) for x in vec[:3]]
        print(f"[1] 单条向量化 OK：{elapsed:.1f}s，维度={len(vec)}，前3维={head}")
        if len(vec) != DIMENSIONS:
            ok = False
            print(f"    [WARN] 维度与请求（{DIMENSIONS}）不一致，请检查")
        if all(x == 0 for x in vec):
            ok = False
            print("    [WARN] 返回全零向量（异常）")
    except Exception as exc:  # noqa: BLE001 - 检查脚本需要打印全部失败原因
        ok = False
        print(f"[1] 单条向量化 FAIL：{_safe_message(exc, api_key)}")

    # 2) 批量文本（3 条）
    if ok:
        try:
            t0 = time.monotonic()
            vecs = embeddings.embed_documents(
                [
                    "天气不错，适合出门散步。",
                    "机器学习是人工智能的一个分支。",
                    "今天学习的主题是向量数据库。",
                ]
            )
            elapsed = time.monotonic() - t0
            dims = sorted({len(v) for v in vecs})
            print(f"[2] 批量向量化 OK：{elapsed:.1f}s，返回 {len(vecs)} 条，维度集合={dims}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"[2] 批量向量化 FAIL：{_safe_message(exc, api_key)}")

    # 3) 对照：check_embedding_ctx_length=True（预期失败——验证必须关闭）
    try:
        embeddings_bad = build_embeddings(api_key, base_url, ctx_length_check=True)
        t0 = time.monotonic()
        vec = embeddings_bad.embed_query("对照测试")
        elapsed = time.monotonic() - t0
        print(
            f"[3] 对照（ctx_length=True）意外成功：{elapsed:.1f}s，维度={len(vec)}"
            " —— 记录：该端点兼容 token 数组输入"
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[3] 对照（ctx_length=True）预期失败：{_safe_message(exc, api_key)}")
        print("    → 证实必须使用 check_embedding_ctx_length=False（设计已配置）")

    print("-" * 46)
    if ok:
        print("结论：百炼 text-embedding-v4 连通正常，可用于资料库向量化。")
        return 0
    print("结论：存在失败项，请检查 .env 配置与网络后重试。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
