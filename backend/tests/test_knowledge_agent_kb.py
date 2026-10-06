"""知识获取 Agent 资料库扩展测试（add-rag-knowledge-base 任务 5.2）。

覆盖：工具注入条件（有/无文档、纯资料库场景）/ kb_search 工具行为（user_id 注入、
异常降级、无 user_id、返回值结构）/ 解析扩展（library 来源、去重、混合来源）/
is_enabled(user_id) 语义。全部离线（patch 检索器、构建函数与文档状态查询）。
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.config import get_settings
from app.services import knowledge_agent
from app.services.kb_retriever import KbHit
from app.services.knowledge_agent import _parse_agent_result

LONG_TEXT = "这是一段内容足够长的资料片段，用于满足有效内容的最小长度阈值。" * 3


@pytest.fixture(autouse=True)
def _cleanup_agent_state():
    yield
    get_settings.cache_clear()
    knowledge_agent._reset_agent_cache()


def _set_env(monkeypatch, **env) -> None:
    base = {
        "TAVILY_API_KEY": "tvly-test-key",
        "DASHSCOPE_API_KEY": "sk-test-key",
        "SEARCH_SUMMARY_MAX_CHARS": "5000",
    }
    base.update(env)
    for key, value in base.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


class FakeAgent:
    def __init__(self, result=None):
        self._result = result if result is not None else {"messages": []}
        self.config = None

    def invoke(self, inputs, config=None):  # noqa: ANN001
        self.config = config
        return self._result


def _tool_text(out) -> str:  # noqa: ANN001
    """工具调用结果 → 文本（ToolMessage 或原始字符串）。"""
    return out.content if hasattr(out, "content") else str(out)


class TestToolInjection:
    """工具注入条件：用户有就绪文档才包含 kb_search。"""

    def test_no_ready_documents_no_kb(self, monkeypatch):
        _set_env(monkeypatch)
        monkeypatch.setattr(knowledge_agent, "_user_has_ready_documents", lambda uid: False)
        captured: dict = {}

        def fake_build(include_kb=False):
            captured["include_kb"] = include_kb
            return FakeAgent()

        monkeypatch.setattr(knowledge_agent, "_build_agent", fake_build)
        knowledge_agent.acquire_knowledge("主题", user_id=7)
        assert captured["include_kb"] is False

    def test_with_ready_documents_injects_kb(self, monkeypatch):
        _set_env(monkeypatch)
        monkeypatch.setattr(knowledge_agent, "_user_has_ready_documents", lambda uid: True)
        captured: dict = {}

        def fake_build(include_kb=False):
            captured["include_kb"] = include_kb
            return FakeAgent()

        monkeypatch.setattr(knowledge_agent, "_build_agent", fake_build)
        knowledge_agent.acquire_knowledge("主题", user_id=7)
        assert captured["include_kb"] is True

    def test_config_carries_user_id(self, monkeypatch):
        _set_env(monkeypatch)
        monkeypatch.setattr(knowledge_agent, "_user_has_ready_documents", lambda uid: True)
        fake = FakeAgent()
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda include_kb=False: fake)

        knowledge_agent.acquire_knowledge("主题", user_id=42)

        assert fake.config["configurable"]["user_id"] == 42

    def test_kb_only_still_runs_agent(self, monkeypatch):
        """无 Tavily 但用户有资料库 → 仍走 Agent 流程（纯资料库场景）。"""
        _set_env(monkeypatch, TAVILY_API_KEY="")
        monkeypatch.setattr(knowledge_agent, "_user_has_ready_documents", lambda uid: True)
        fake = FakeAgent()
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda include_kb=False: fake)

        result = knowledge_agent.acquire_knowledge("主题", user_id=7)

        assert isinstance(result, knowledge_agent.KnowledgeResult)

    def test_no_channel_returns_empty(self, monkeypatch):
        """无 Tavily 且无资料库 → 空结果（与升级前行为一致）。"""
        _set_env(monkeypatch, TAVILY_API_KEY="")
        monkeypatch.setattr(knowledge_agent, "_user_has_ready_documents", lambda uid: False)
        called: list = []
        monkeypatch.setattr(knowledge_agent, "_build_agent", lambda include_kb=False: called.append(1))

        result = knowledge_agent.acquire_knowledge("主题", user_id=7)

        assert result.has_valid_content is False
        assert result.trace["library_search_count"] == 0
        assert called == [], "无可用渠道时不应构建 Agent"


class TestKbSearchTool:
    """kb_search 工具行为（config 注入 user_id / 异常降级 / 返回结构）。"""

    def _build(self, monkeypatch, hits=None, exc: Exception | None = None):
        settings = SimpleNamespace(kb_snippet_max_chars=50)
        if exc is not None:
            def _raise(uid, query):  # noqa: ANN001
                raise exc

            monkeypatch.setattr(knowledge_agent, "search_knowledge_base", _raise)
        else:
            monkeypatch.setattr(knowledge_agent, "search_knowledge_base", lambda uid, q: list(hits or []))
        return knowledge_agent._build_kb_tool(settings)

    def _invoke(self, tool, query: str = "q", user_id: int | None = 7) -> str:
        out = tool.invoke(
            {"type": "tool_call", "name": "kb_search", "args": {"query": query}, "id": "c1"},
            config={"configurable": {"user_id": user_id}},
        )
        return _tool_text(out)

    def test_returns_json_payload(self, monkeypatch):
        hits = [KbHit(text="命中片段内容", filename="讲义.pdf", doc_id="doc_x", distance=0.1)]
        tool = self._build(monkeypatch, hits=hits)

        payload = json.loads(self._invoke(tool))

        assert payload["results"][0]["filename"] == "讲义.pdf"
        assert payload["results"][0]["score"] == pytest.approx(0.9)
        assert payload["results"][0]["content"] == "命中片段内容"

    def test_content_truncated(self, monkeypatch):
        hits = [KbHit(text="长" * 200, filename="a.md", doc_id="d", distance=0.2)]
        tool = self._build(monkeypatch, hits=hits)
        payload = json.loads(self._invoke(tool))
        assert len(payload["results"][0]["content"]) == 50  # kb_snippet_max_chars

    def test_no_hits_message(self, monkeypatch):
        tool = self._build(monkeypatch, hits=[])
        assert "没有与该查询相关的内容" in self._invoke(tool)

    def test_exception_degrades_to_message(self, monkeypatch):
        tool = self._build(monkeypatch, exc=RuntimeError("chroma down"))
        assert "资料库暂时不可用" in self._invoke(tool)

    def test_no_user_id_returns_hint(self, monkeypatch):
        tool = self._build(monkeypatch)
        assert "暂无可用资料库内容" in self._invoke(tool, user_id=None)

    def test_args_schema_excludes_config(self, monkeypatch):
        tool = self._build(monkeypatch)
        props = list(tool.args_schema.model_json_schema().get("properties", {}).keys())
        assert props == ["query"]  # config 为注入参数，不暴露给 LLM


class TestParseLibraryResults:
    """_parse_agent_result 对资料库工具消息的解析（来源 / 统计 / 判定）。"""

    def _messages(self) -> list:
        return [
            HumanMessage(content="根据我的资料出题"),
            AIMessage(
                content="",
                tool_calls=[{"name": "kb_search", "args": {"query": "RAG 流程"}, "id": "k1"}],
            ),
            ToolMessage(
                content=json.dumps(
                    {"results": [{"filename": "讲义.pdf", "content": LONG_TEXT, "score": 0.9}]},
                    ensure_ascii=False,
                ),
                tool_call_id="k1",
                name="kb_search",
            ),
            AIMessage(content="领域判断：基于用户资料。"),
        ]

    def test_library_sources_and_trace(self):
        result = _parse_agent_result({"messages": self._messages()}, max_summary_chars=5000)

        assert result.has_valid_content is True
        assert result.sources == [{"type": "library", "title": "讲义.pdf"}]
        assert result.trace["library_search_count"] == 1
        assert result.trace["library_hit_count"] == 1
        assert result.trace["doc_count"] == 1
        assert result.trace["search_count"] == 0
        assert "RAG 流程" in result.trace["queries"]

    def test_short_library_content_not_valid(self):
        messages = self._messages()
        messages[2] = ToolMessage(
            content=json.dumps({"results": [{"filename": "x.pdf", "content": "太短"}]}, ensure_ascii=False),
            tool_call_id="k1",
            name="kb_search",
        )
        result = _parse_agent_result({"messages": messages}, max_summary_chars=100)
        assert result.has_valid_content is False

    def test_library_dedup_by_filename(self):
        messages = [
            AIMessage(content="", tool_calls=[{"name": "kb_search", "args": {"query": "a"}, "id": "k1"}]),
            ToolMessage(
                content=json.dumps(
                    {
                        "results": [
                            {"filename": "同一文档.pdf", "content": LONG_TEXT},
                            {"filename": "同一文档.pdf", "content": LONG_TEXT},
                        ]
                    },
                    ensure_ascii=False,
                ),
                tool_call_id="k1",
                name="kb_search",
            ),
        ]
        result = _parse_agent_result({"messages": messages}, max_summary_chars=100)

        assert [s["title"] for s in result.sources] == ["同一文档.pdf"]
        assert result.trace["library_hit_count"] == 2

    def test_web_and_library_mixed(self):
        messages = self._messages()
        messages.insert(
            -1,
            AIMessage(content="", tool_calls=[{"name": "tavily_search_basic", "args": {"query": "q"}, "id": "w1"}]),
        )
        messages.insert(
            -1,
            ToolMessage(
                content=json.dumps(
                    {"results": [{"url": "https://a.example/1", "title": "网文", "content": LONG_TEXT}]},
                    ensure_ascii=False,
                ),
                tool_call_id="w1",
                name="tavily_search_basic",
            ),
        )
        result = _parse_agent_result({"messages": messages}, max_summary_chars=5000)

        types = [s["type"] for s in result.sources]
        assert "library" in types and "web" in types
        assert result.trace["search_count"] == 1
        assert result.trace["library_search_count"] == 1


class TestIsEnabled:
    """is_enabled 语义：联网凭据或（百炼 + 该用户有就绪文档）。"""

    def test_tavily_enabled_backward_compatible(self, monkeypatch):
        _set_env(monkeypatch)
        assert knowledge_agent.is_enabled() is True  # 旧调用（无 user_id）语义不变

    def test_kb_only_requires_ready_documents(self, monkeypatch):
        _set_env(monkeypatch, TAVILY_API_KEY="")
        monkeypatch.setattr(knowledge_agent, "_user_has_ready_documents", lambda uid: True)
        assert knowledge_agent.is_enabled(user_id=7) is True

    def test_kb_without_documents_disabled(self, monkeypatch):
        _set_env(monkeypatch, TAVILY_API_KEY="")
        monkeypatch.setattr(knowledge_agent, "_user_has_ready_documents", lambda uid: False)
        assert knowledge_agent.is_enabled(user_id=7) is False

    def test_no_credentials_disabled(self, monkeypatch):
        _set_env(monkeypatch, TAVILY_API_KEY="", DASHSCOPE_API_KEY="")
        assert knowledge_agent.is_enabled(user_id=7) is False
