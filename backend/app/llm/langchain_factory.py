"""LangChain 模型工厂：统一初始化 DeepSeek（OpenAI 兼容接口）。

说明：
- 底层 SDK 级重试关闭（max_retries=0），重试策略统一由业务层控制，
  避免“SDK 重试 × 业务重试”叠加放大请求量。
- 未配置 API Key 时用占位符初始化，保证服务可启动；真正调用时会返回错误并由业务层兜底。
"""
from __future__ import annotations

from langchain_openai import ChatOpenAI

from app.core.config import get_settings


def create_chat_model(temperature: float | None = None) -> ChatOpenAI:
    """创建 DeepSeek 对话模型实例。"""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        api_key=settings.deepseek_api_key or "sk-not-configured",
        temperature=settings.quiz_temperature if temperature is None else temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )
