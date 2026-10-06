"""配置项测试：知识获取 / 异步任务相关默认值与映射（对应任务 1.2）。

说明：
- 用 `Settings(_env_file=None)` 构造，隔离本机 .env 的真实值；
- 同时清理相关环境变量，保证断言的是代码默认值；
- 旧版"固定检索流程"的配置项从未落地，这里断言其不存在，防止回潮。
"""
from __future__ import annotations

import pytest

from app.core.config import Settings

NEW_CONFIG_ENV_KEYS = [
    "TAVILY_API_KEY",
    "SEARCH_AGENT_TIMEOUT_SECONDS",
    "SEARCH_AGENT_MAX_TOOL_CALLS",
    "SEARCH_MAX_RESULTS",
    "SEARCH_SUMMARY_MAX_CHARS",
    "SEARCH_COUNTRY",
    "SEARCH_AUTO_PARAMETERS",
    "ASSESSMENT_TIMEOUT_SECONDS",
    "TASK_TTL_HOURS",
    "TASK_WORKER_CONCURRENCY",
]

LEGACY_FIELD_NAMES = ["search_timeout_seconds", "search_score_threshold", "search_snippet_max_chars"]


@pytest.fixture()
def clean_settings(monkeypatch) -> Settings:
    """无环境变量干扰的 Settings 实例（不读 .env）。"""
    for key in NEW_CONFIG_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return Settings(_env_file=None)


class TestSearchSettingsDefaults:
    """知识获取配置默认值。"""

    def test_knowledge_acquisition_disabled_by_default(self, clean_settings: Settings):
        assert clean_settings.tavily_api_key == ""  # 空 = 未启用（兼容模式）

    def test_agent_guardrails_defaults(self, clean_settings: Settings):
        assert clean_settings.search_agent_timeout_seconds == 45.0
        assert clean_settings.search_agent_max_tool_calls == 4

    def test_search_scope_defaults(self, clean_settings: Settings):
        assert clean_settings.search_max_results == 10
        assert clean_settings.search_summary_max_chars == 5000

    def test_region_and_auto_parameters_defaults(self, clean_settings: Settings):
        assert clean_settings.search_country == ""  # 默认不偏向
        assert clean_settings.search_auto_parameters is True

    def test_env_override_maps_to_settings(self, monkeypatch):
        """环境变量映射校验：TAVILY_API_KEY -> tavily_api_key。"""
        monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key")
        assert Settings(_env_file=None).tavily_api_key == "tvly-test-key"


class TestTaskSettingsDefaults:
    """异步生成任务配置默认值。"""

    def test_assessment_timeout(self, clean_settings: Settings):
        assert clean_settings.assessment_timeout_seconds == 20.0

    def test_task_lifecycle_defaults(self, clean_settings: Settings):
        assert clean_settings.task_ttl_hours == 24
        assert clean_settings.task_worker_concurrency == 2


class TestLegacyFieldsRemoved:
    """旧“固定检索流程”设计遗留配置项不得存在。"""

    def test_legacy_fields_not_present(self):
        for name in LEGACY_FIELD_NAMES:
            assert name not in Settings.model_fields, f"不应存在旧配置项：{name}"
