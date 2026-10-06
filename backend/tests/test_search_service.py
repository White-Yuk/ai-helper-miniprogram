"""知识获取 Agent 边界测试（任务 2.3）。

原则：全部离线——patch `_build_agent` / 直接调用解析与回调函数；
不触碰真实 Tavily / LLM（真实联调见 tasks 9.2）。
"""
from __future__ import annotations

import json
import time

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.config import get_settings
from app.services import knowledge_agent
from app.services.knowledge_agent import (
    _StepCallback,
    _build_tools,
    _parse_agent_result,
    _parse_tool_content,
    acquire_knowledge,
    is_enabled,
)

LONG_TEXT = "这是一段内容足够长的资料片段，用于满足有效内容的最小长度阈值。" * 3


def _set_env(monkeypatch, **env) -> None:
    """写入测试环境变量并刷新配置缓存。"""
    base = {
        "TAVILY_API_KEY": "tvly-test-key",
        "SEARCH_AGENT_TIMEOUT_SECONDS": "45",
        "SEARCH_SUMMARY_MAX_CHARS": "5000",
    }
    base.update(env)
    for key, value in base.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _cleanup_agent_state():
    """每个用例后恢复全局状态（配置缓存 + Agent 缓存）。"""
    yield
    get_settings.cache_clear()
    knowledge_agent._reset_agent_cache()


class FakeAgent:
    """模拟 Agent 的 invoke 行为（返回消息列表 / 抛异常 / 延时）。"""

    def __init__(self, result=None, exc: Exception | None = None, delay: float = 0.0):
        self._result = result if result is not None else {"messages": []}
        self._exc = exc
        self._delay = delay
        self.config: dict | None = None
        self.inputs = None

    def invoke(self, inputs, config=None):  # noqa: ANN001
        self.inputs = inputs
        self.config = config
        if self._delay:
            time.sleep(self._delay)
        if self._exc is not None:
            raise self._exc
        return self._result


def _tool_output(query: str, items: list[dict]) -> str:
    return json.dumps({"query": query, "results": items}, ensure_ascii=False)


def _search_messages(query: str, items: list[dict]) -> list:
    return [
        HumanMessage(content=query),
        AIMessage(
            content="",
            tool_calls=[{"name": "tavily_search_basic", "args": {"query": query}, "id": "t1"}],
        ),
        ToolMessage(content=_tool_output(query, items), tool_call_id="t1", name="tavily_search_basic"),
        AIMessage(content=f"领域判断：AI 工程。要点：{query} 属于 AI 工程实践。"),
    ]


class TestAcquireBoundaries:
    """acquire_knowledge 的降级边界（开关 / 超时 / 异常 / 构建失败）。"""

    def test_disabled_returns_empty_without_build(self, monkeypatch):
        _set_env(monkeypatch, TAVILY_API_KEY="")
        called: list[int] = []
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda: called.append(1))

        result = acquire_knowledge("什么是 HTTP")

        assert result.has_valid_content is False
        assert result.summary == ""
        assert result.sources == []
        assert result.trace["search_count"] == 0
        assert called == [], "未配置 Key 时不应构建 Agent"
        assert is_enabled() is False

    def test_agent_timeout_degrades(self, monkeypatch):
        _set_env(monkeypatch, SEARCH_AGENT_TIMEOUT_SECONDS="0.05")
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda: FakeAgent(delay=0.3))

        result = acquire_knowledge("Harness Engineering")

        assert result.has_valid_content is False
        assert result.summary == ""

    def test_agent_exception_degrades(self, monkeypatch):
        _set_env(monkeypatch)
        monkeypatch.setattr(
            knowledge_agent, "_build_agent", lambda: FakeAgent(exc=RuntimeError("network down"))
        )

        result = acquire_knowledge("Harness Engineering")

        assert result.has_valid_content is False
        assert result.trace["doc_count"] == 0

    def test_build_failure_degrades(self, monkeypatch):
        _set_env(monkeypatch)

        def _raise():
            raise ValueError("bad key")

        monkeypatch.setattr(knowledge_agent, "_build_agent", _raise)

        result = acquire_knowledge("Harness Engineering")

        assert result.has_valid_content is False
        assert result.summary == ""


class TestAcquireParsing:
    """成功路径：摘要 / 来源 / 溯源 / 截断。"""

    def test_success_parses_summary_sources_trace(self, monkeypatch):
        _set_env(monkeypatch)
        messages = _search_messages(
            "Harness Engineering",
            [
                {"title": "Harness Engineering 导论", "url": "https://a.example/1", "content": LONG_TEXT},
                {"title": "短片段", "url": "https://a.example/2", "content": "太短"},
            ],
        )
        fake = FakeAgent(result={"messages": messages})
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda: fake)

        result = acquire_knowledge("Harness Engineering")

        assert result.has_valid_content is True
        assert "AI 工程" in result.summary
        assert result.sources == [
            {"title": "Harness Engineering 导论", "url": "https://a.example/1"},
            {"title": "短片段", "url": "https://a.example/2"},
        ]
        assert result.trace == {
            "search_count": 1,
            "extract_count": 0,
            "queries": ["Harness Engineering"],
            "doc_count": 2,
        }

    def test_summary_truncated_by_config(self, monkeypatch):
        _set_env(monkeypatch, SEARCH_SUMMARY_MAX_CHARS="20")
        messages = [
            HumanMessage(content="主题"),
            AIMessage(content="长" * 100),
        ]
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda: FakeAgent(result={"messages": messages}))

        result = acquire_knowledge("主题")

        assert len(result.summary) == 20

    def test_sources_deduped_and_capped(self, monkeypatch):
        _set_env(monkeypatch)
        items = [{"title": f"t{i}", "url": f"https://a.example/{i}", "content": LONG_TEXT} for i in range(12)]
        items.append({"title": "重复", "url": "https://a.example/0", "content": LONG_TEXT})
        monkeypatch.setattr(
            knowledge_agent, "_build_agent", lambda: FakeAgent(result={"messages": _search_messages("q", items)})
        )

        result = acquire_knowledge("q")

        urls = [s["url"] for s in result.sources]
        assert len(urls) == 10
        assert len(set(urls)) == len(urls)

    def test_error_tool_message_ignored(self, monkeypatch):
        _set_env(monkeypatch)
        messages = [
            HumanMessage(content="冷门主题"),
            AIMessage(
                content="",
                tool_calls=[{"name": "tavily_search_basic", "args": {"query": "冷门主题"}, "id": "t1"}],
            ),
            ToolMessage(
                content="No search results found for '冷门主题'. Suggestions: ...",
                tool_call_id="t1",
                name="tavily_search_basic",
            ),
            AIMessage(content="未找到相关资料。"),
        ]
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda: FakeAgent(result={"messages": messages}))

        result = acquire_knowledge("冷门主题")

        assert result.has_valid_content is False
        assert result.trace["doc_count"] == 0
        assert "未找到相关资料" in result.summary  # 结论照实带回（供守卫流程判断）

    def test_extract_result_parsed(self, monkeypatch):
        _set_env(monkeypatch)
        extract_output = json.dumps(
            {"results": [{"url": "https://page.example/post", "raw_content": LONG_TEXT}], "failed_results": []},
            ensure_ascii=False,
        )
        messages = [
            HumanMessage(content="https://page.example/post"),
            AIMessage(
                content="",
                tool_calls=[{"name": "tavily_extract", "args": {"urls": ["https://page.example/post"]}, "id": "t2"}],
            ),
            ToolMessage(content=extract_output, tool_call_id="t2", name="tavily_extract"),
            AIMessage(content="领域判断：网页主题要点。"),
        ]
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda: FakeAgent(result={"messages": messages}))

        result = acquire_knowledge("https://page.example/post")

        assert result.has_valid_content is True
        assert result.sources == [{"title": "https://page.example/post", "url": "https://page.example/post"}]
        assert result.trace["extract_count"] == 1
        assert result.trace["search_count"] == 0

    def test_agent_invoke_config_has_callbacks_and_recursion_limit(self, monkeypatch):
        _set_env(monkeypatch)
        messages = _search_messages("q", [{"title": "t", "url": "https://a.example/1", "content": LONG_TEXT}])
        fake = FakeAgent(result={"messages": messages})
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda: fake)
        steps: list = []

        acquire_knowledge("q", on_step=lambda *args: steps.append(args))

        assert fake.config is not None
        callbacks = fake.config.get("callbacks")
        assert callbacks and isinstance(callbacks[0], _StepCallback)
        assert fake.config.get("recursion_limit") == knowledge_agent.AGENT_RECURSION_LIMIT
        assert fake.inputs["messages"][0]["content"] == "q"

    def test_no_on_step_means_no_callbacks(self, monkeypatch):
        _set_env(monkeypatch)
        fake = FakeAgent(result={"messages": []})
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda: fake)

        acquire_knowledge("q")

        assert fake.config.get("callbacks") == []


class TestStepCallback:
    """工具事件 → 任务步骤（key=run_id，同调用可更新）。"""

    def test_search_start_and_end(self):
        events: list = []
        handler = _StepCallback(lambda *args: events.append(args))

        handler.on_tool_start(
            {"name": "tavily_search_basic"}, json.dumps({"query": "RAG 是什么"}), run_id="run-1"
        )
        handler.on_tool_end({"results": [1, 2, 3]}, run_id="run-1")

        assert events[0] == ("run-1", "联网搜索", "搜索词：RAG 是什么", "doing")
        assert events[1] == ("run-1", "联网搜索", "获得 3 条资料", "done")

    def test_extract_input_described(self):
        events: list = []
        handler = _StepCallback(lambda *args: events.append(args))

        handler.on_tool_start(
            {"name": "tavily_extract"}, json.dumps({"urls": ["https://a.example/post"]}), run_id="run-2"
        )

        assert events[0] == ("run-2", "网页提取", "提取：https://a.example/post", "doing")

    def test_error_output_and_tool_error(self):
        events: list = []
        handler = _StepCallback(lambda *args: events.append(args))

        handler.on_tool_start({"name": "tavily_search_deep"}, json.dumps({"query": "x"}), run_id="run-3")
        handler.on_tool_end("No search results found for 'x'.", run_id="run-3")
        handler.on_tool_error(TimeoutError("too slow"), run_id="run-4")

        assert events[1] == ("run-3", "深度检索", "未获得资料", "done")
        assert events[2] == ("run-4", "获取资料", "调用失败（已自动降级）", "done")

    def test_python_repr_input_described(self):
        """Agent 路径 on_tool_start 的 input_str 是 Python repr（单引号）→ 需 literal_eval 兼容。"""
        events: list = []
        handler = _StepCallback(lambda *args: events.append(args))

        handler.on_tool_start({"name": "tavily_search_basic"}, "{'query': 'Harness Engineering'}", run_id="run-5")

        assert events[0] == ("run-5", "联网搜索", "搜索词：Harness Engineering", "doing")

    def test_tool_message_output_described(self):
        """Agent（ToolNode）路径 on_tool_end 收到 ToolMessage（content 为 JSON 字符串）。"""
        from langchain_core.messages import ToolMessage

        events: list = []
        handler = _StepCallback(lambda *args: events.append(args))
        message = ToolMessage(
            content=json.dumps({"results": [1, 2, 3], "query": "x"}), tool_call_id="t1", name="tavily_search_basic"
        )

        handler.on_tool_end(message, run_id="run-6")

        assert events[0] == ("run-6", "获取资料", "获得 3 条资料", "done")


class TestParseHelpers:
    """内容解析容错。"""

    def test_parse_tool_content_variants(self):
        assert _parse_tool_content({"results": []}) == {"results": []}
        assert _parse_tool_content('{"results": [1]}') == {"results": [1]}
        assert _parse_tool_content("plain error text") is None
        assert _parse_tool_content("[1, 2]") is None
        assert _parse_tool_content([{"type": "text", "text": '{"results": []}'}]) == {"results": []}
        assert _parse_tool_content(None) is None

    def test_parse_agent_result_handles_missing_messages(self):
        result = _parse_agent_result({}, max_summary_chars=100)
        assert result.has_valid_content is False
        assert result.trace["search_count"] == 0


class TestToolConstruction:
    """C 方案档位构造（离线断言实例参数；不触网）。"""

    def _tools(self, monkeypatch, **env):
        _set_env(monkeypatch, TAVILY_API_KEY="tvly-fake-key", **env)
        tools = _build_tools(get_settings())
        return {tool.name: tool for tool in tools}

    def test_tool_names(self, monkeypatch):
        tools = self._tools(monkeypatch)
        assert list(tools) == ["tavily_search_basic", "tavily_search_deep", "tavily_extract"]

    def test_basic_tier_locked_light(self, monkeypatch):
        tools = self._tools(monkeypatch)
        basic = tools["tavily_search_basic"]
        assert basic.max_results == 10
        assert basic.include_raw_content is False
        assert basic.search_depth == "basic"  # 档位有意锁定
        assert basic.auto_parameters is False  # 关闭自动参数（锁定 1 credit）

    def test_deep_tier_allows_auto_upgrade(self, monkeypatch):
        tools = self._tools(monkeypatch)
        deep = tools["tavily_search_deep"]
        assert deep.max_results == knowledge_agent.DEEP_SEARCH_MAX_RESULTS == 5
        assert deep.include_raw_content is True
        assert deep.auto_parameters is True
        # 实例化不设动态参数（避免压制运行时值 / 自动升级）
        assert deep.search_depth is None
        assert deep.topic is None
        assert deep.include_domains is None
        assert deep.exclude_domains is None
        # 深度档 schema 默认值放宽（否则 _parse_input 会填 basic/general 压制自动升级）
        assert deep.args_schema is knowledge_agent._DeepSearchInput
        omitted = deep.args_schema.model_validate({"query": "x"})
        assert omitted.search_depth is None
        assert omitted.topic is None

    def test_extract_depth_not_preset(self, monkeypatch):
        tools = self._tools(monkeypatch)
        assert tools["tavily_extract"].extract_depth is None

    def test_country_mapping(self, monkeypatch):
        tools = self._tools(monkeypatch, SEARCH_COUNTRY="china")
        assert tools["tavily_search_basic"].country == "china"
        assert tools["tavily_search_deep"].country == "china"

    def test_country_empty_maps_to_none(self, monkeypatch):
        tools = self._tools(monkeypatch, SEARCH_COUNTRY="")
        assert tools["tavily_search_basic"].country is None

    def test_single_agent_cached(self, monkeypatch):
        _set_env(monkeypatch, TAVILY_API_KEY="tvly-fake-key")
        first = knowledge_agent._build_agent()
        second = knowledge_agent._build_agent()
        assert first is second
