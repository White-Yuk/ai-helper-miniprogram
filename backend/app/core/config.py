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

    # ---- 知识获取（Tavily 联网检索；tavily_api_key 为空 = 未启用，行为与升级前一致） ----
    tavily_api_key: str = ""
    # Agent 外层超时（线程池 future.result 兜底；超时按“无有效内容”降级）
    search_agent_timeout_seconds: float = 45.0
    # 写入 Agent Prompt 的工具调用次数上限
    search_agent_max_tool_calls: int = 4
    # 轻快档（basic）搜索工具的结果条数；深度档固定 5 条完整内容（见 knowledge_agent 常量）
    search_max_results: int = 10
    # 注入出题 Prompt 的知识摘要截断上限（字符）
    search_summary_max_chars: int = 5000
    # 检索结果地域偏向（国家名如 china；空 = 不偏向；仅 general 主题生效）
    search_country: str = ""
    # 仅作用于深度档：允许 Tavily 自动配置参数（可能升级 advanced → 约 2 credits/次）
    search_auto_parameters: bool = True

    # ---- 异步生成任务（异步任务 + 轮询） ----
    # 知识可靠性评估调用超时
    assessment_timeout_seconds: float = 20.0
    # 任务保留时长（创建任务时懒清理超期任务）
    task_ttl_hours: int = 24
    # 任务执行线程池并发数
    task_worker_concurrency: int = 2

    # ---- 数据库（MySQL） ----
    # 可选：完整 SQLAlchemy URL（非空时优先使用；一般不需要填）
    database_url: str = ""
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    # ★ 只需在 .env 中填写 DB_PASSWORD 即可
    db_password: str = ""
    db_name: str = "ai_quiz"

    # ---- 登录鉴权（JWT） ----
    jwt_secret: str = "dev-secret-change-me"
    jwt_expire_days: int = 30

    # ---- 微信小程序 ----
    wechat_appid: str = ""
    wechat_secret: str = ""
    # true=开启开发态模拟登录（仅本地调试用；接入真实微信登录后置为 false）
    auth_mock_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def db_url(self) -> str:
        """组装 SQLAlchemy 数据库 URL（密码自动 URL 编码，支持任意特殊字符）。"""
        if self.database_url:
            return self.database_url
        from urllib.parse import quote_plus

        return (
            f"mysql+pymysql://{self.db_user}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
