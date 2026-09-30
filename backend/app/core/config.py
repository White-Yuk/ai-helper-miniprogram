"""应用配置：从环境变量 / .env 读取（pydantic-settings）。"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。字段名与环境变量不区分大小写（DEEPSEEK_API_KEY -> deepseek_api_key）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 服务基础 ----
    app_name: str = "AI 闯关学习"
    app_env: str = "development"
    debug: bool = True
    version: str = "0.1.0"
    # 允许的跨域来源，逗号分隔；开发期默认 *
    cors_origins: str = "*"

    # ---- DeepSeek ----
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # ---- LLM 调用参数 ----
    quiz_temperature: float = 0.4
    report_temperature: float = 0.5
    llm_timeout_seconds: float = 60.0
    # 失败后的重试次数（不含首次调用）；总尝试次数 = llm_max_retries + 1
    llm_max_retries: int = 2

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
