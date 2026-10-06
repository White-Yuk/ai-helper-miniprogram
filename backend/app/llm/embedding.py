"""Embedding 工厂：LangChain OpenAIEmbeddings 对接阿里云百炼（DashScope）。

对齐 design.md D4：
- 模型 text-embedding-v4（中文效果好、按量计费有免费额度）；
- `check_embedding_ctx_length=False`：对接非 OpenAI 端点必须——本项目实测
  （scripts/check_dashscope.py）：开启时会把 tiktoken token 数组发给百炼，
  返回 400 InvalidParameter（contents is neither str nor list of str）；
- chunk_size 对齐百炼单请求条数上限（默认 10 条/请求）；
- 未配置 API Key 时抛 EmbeddingNotConfiguredError（调用方转可读提示）。
"""
from __future__ import annotations

from langchain_openai import OpenAIEmbeddings

from app.core.config import get_settings


class EmbeddingNotConfiguredError(RuntimeError):
    """未配置百炼凭据（资料库功能未启用）。"""


def is_embedding_enabled() -> bool:
    """Embedding 能力是否启用（凭据已配置）。"""
    return bool(get_settings().dashscope_api_key)


def build_embeddings() -> OpenAIEmbeddings:
    """构建百炼 Embedding 实例（每次调用返回新实例，无状态）。

    注意：dimensions 与已建向量库绑定，变更需重建向量库（见 design D4）。
    """
    settings = get_settings()
    if not settings.dashscope_api_key:
        raise EmbeddingNotConfiguredError("未配置 DASHSCOPE_API_KEY，资料库功能未启用")
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        base_url=settings.dashscope_base_url,
        api_key=settings.dashscope_api_key,
        dimensions=settings.embedding_dimensions,
        check_embedding_ctx_length=False,  # 百炼必须：原样发文本，禁用 tiktoken 分词
        chunk_size=settings.embedding_batch_size,  # 对齐百炼单请求条数上限
        max_retries=1,  # 失败轻试重试 1 次（对齐项目模式）
    )
