"""知识获取 Agent：出题前的联网检索 / 网页提取（Tavily）。

对齐 design.md D2 / D3：
- create_agent + 3 个工具（轻快档 basic / 深度档 deep / 网页提取 extract），构建结果进程级缓存；
- 45s 外层超时（单线程 executor 的 future.result 兜底）；构建 / 调用异常、超时 → 返回
  "无有效内容"信号（不向外抛异常），交由编排层降级处理；
- 有效内容判定与来源提取均基于工具消息（ToolMessage）的真实执行结果，不依赖 Agent 自报；
- 摘要按 search_summary_max_chars 截断后供注入出题链路。

源码级核对（langchain-tavily 0.2.18，2026-10-06）：
- `max_results` / `include_raw_content` / `auto_parameters` / `country` 等属"仅实例化参数"，
  运行时传入会直接报错（forbidden_params）→ 以双实例分档承载（basic 宽 / deep 深）；
- "实例值优先于运行时值"（`self.X if self.X else 运行时值`）→ 除档位有意锁定项（basic 档
  的 search_depth）外，实例化时不得设置可动态参数（time_range / topic / include_domains 等）；
- `BaseTool._parse_input` 会把 args_schema 的"显式默认值"填入调用参数（即使模型未传）→
  深度档用子类 schema 将 search_depth / topic / include_domains / exclude_domains 缺省为 None，
  否则默认值（basic / general / []）会压制 auto_parameters 的自动升级能力；
- 工具返回 dict；langgraph ToolNode 会把非字符串输出 json.dumps 为字符串后再放进
  ToolMessage.content → 解析时按 JSON 字符串处理（同时兼容 dict）。
"""
from __future__ import annotations

import ast
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, List, Literal, Optional

from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_tavily import TavilyExtract, TavilySearch
from langchain_tavily.tavily_search import TavilySearchInput

from app.core.config import get_settings
from app.llm.langchain_factory import create_chat_model
from app.prompts.agent_prompt import build_agent_system_prompt
from app.services.kb_retriever import search_knowledge_base

logger = logging.getLogger(__name__)

# 深度档搜索结果条数（固定 5 条完整内容：条数少而内容全，控制注入体积）
DEEP_SEARCH_MAX_RESULTS = 5

# 有效内容判定的最小字符阈值（过短视为无实质内容，如空片段 / 错误提示）
MIN_VALID_CONTENT_CHARS = 50

# Agent 递归步数上限（LLM 步 + 工具步；防御性护栏，正常 ≤4 次工具调用不会触达）
AGENT_RECURSION_LIMIT = 12

# 来源条数上限
MAX_SOURCES = 10

# 工具名 → 步骤标签（前端步骤流展示用）
TOOL_STEP_LABELS = {
    "tavily_search_basic": "联网搜索",
    "tavily_search_deep": "深度检索",
    "tavily_extract": "网页提取",
    "kb_search": "资料库检索",
}

# 步骤回调签名：on_step(key, label, detail, state)，state ∈ {doing, done}
StepCallback = Callable[[str, str, str, str], None]


@dataclass
class KnowledgeResult:
    """知识获取结果。

    - summary: Agent 结构化摘录（已按配置截断）；无内容时为空字符串
    - sources: 来源列表 [{title, url}]（从工具消息解析、去重、有上限）
    - trace: 知识溯源摘要 {search_count, extract_count, queries, doc_count}
    - has_valid_content: 是否存在内容有效的工具结果（出题守卫的判定依据）
    """

    summary: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)
    has_valid_content: bool = False


class _DeepSearchInput(TavilySearchInput):
    """深度档输入 schema：可动态参数一律缺省为 None（交由 Agent / auto_parameters 决定）。

    背景：`BaseTool._parse_input` 会把显式默认值填入调用参数——若沿用基类默认
    （search_depth="basic"、topic="general"、include_domains=[]），将压制
    auto_parameters 的自动升级能力（显式值覆盖自动值）。
    """

    search_depth: Optional[Literal["basic", "advanced", "fast", "ultra-fast"]] = None
    topic: Optional[Literal["general", "news", "finance"]] = None
    include_domains: Optional[List[str]] = None
    exclude_domains: Optional[List[str]] = None


# ---- Agent 构建（二态进程级缓存：是否含资料库工具） ----

_agent_cache: dict[bool, Any] = {}


def _reset_agent_cache() -> None:
    """清空 Agent 缓存（测试 / 配置热更新场景使用）。"""
    global _agent_cache
    _agent_cache = {}


def _resolve_country() -> Optional[str]:
    """检索地域偏向：空字符串 = 不偏向（传 None，避免把空值发给 Tavily）。"""
    country = get_settings().search_country.strip()
    return country or None


def _build_tools(settings) -> list:
    """构建 3 个 Tavily 工具（测试可离线断言构造参数）。

    - 轻快档：10 条摘要、锁定 search_depth="basic"、关闭 auto_parameters（1 credit）
    - 深度档：5 条完整内容、auto_parameters 取配置（允许自动升级，约 2 credits）
    - 提取档：不预设 extract_depth（运行时由 Agent 选择）
    """
    key = settings.tavily_api_key
    country = _resolve_country()

    search_basic = TavilySearch(
        name="tavily_search_basic",
        description=(
            "轻快联网搜索：返回 10 条结果摘要。适合常见主题、术语领域判断与广度探索；"
            "该工具已锁定轻快模式（无需传 search_depth），支持 time_range / topic / "
            "include_domains / start_date / end_date 等动态参数。"
        ),
        tavily_api_key=key,
        max_results=settings.search_max_results,
        include_raw_content=False,
        # 档位有意锁定：轻快轨道固定 basic、关闭自动参数（避免自动升级到 advanced → 2 credits）
        search_depth="basic",
        auto_parameters=False,
        country=country,
    )
    search_deep = TavilySearch(
        name="tavily_search_deep",
        description=(
            "深度联网检索：返回 5 条结果的完整页面内容。适合复杂、专业、有歧义或"
            "首轮信息不足的主题；允许 Tavily 自动优化检索参数。支持 time_range / topic / "
            "include_domains / start_date / end_date 等动态参数。"
        ),
        tavily_api_key=key,
        max_results=DEEP_SEARCH_MAX_RESULTS,
        include_raw_content=True,
        # 深度轨道：不预设 search_depth（允许 auto_parameters 自动升级）；其余动态参数保持缺省
        auto_parameters=settings.search_auto_parameters,
        country=country,
    )
    # 深度档：放宽 schema 默认值，避免 "basic"/"general"/[] 压制自动参数
    search_deep.args_schema = _DeepSearchInput

    extract = TavilyExtract(
        name="tavily_extract",
        description=(
            "提取指定网页的完整内容（输入 urls 列表）。用户输入包含网址时必须使用；"
            "可按需选择 extract_depth（advanced 成功率更高但更慢）；"
            "提取失败时请改用关键词搜索补救。"
        ),
        tavily_api_key=key,
        # extract_depth 不预设：由 Agent 按页面情况动态选择
    )

    return [search_basic, search_deep, extract]


def _build_agent(include_kb: bool = False):
    """构建知识获取 Agent（按「是否含资料库工具」二态进程级缓存；测试可 patch 本函数）。

    include_kb=True：工具集中加入「资料库检索」工具（仅当用户有就绪文档，
    由 acquire_knowledge 判断后传入）。
    """
    cached = _agent_cache.get(include_kb)
    if cached is not None:
        return cached
    settings = get_settings()
    tools = _build_tools(settings) if settings.tavily_api_key else []
    if include_kb:
        tools.append(_build_kb_tool(settings))
    agent = create_agent(
        create_chat_model(),
        tools=tools,
        system_prompt=build_agent_system_prompt(settings.search_agent_max_tool_calls),
    )
    _agent_cache[include_kb] = agent
    return agent


def _build_kb_tool(settings):
    """构建「资料库检索」工具（user_id 经运行时 config 注入，严格按用户隔离）。"""
    snippet_max = settings.kb_snippet_max_chars

    @tool("kb_search")
    def kb_search(query: str, config: RunnableConfig) -> str:
        """检索用户本人上传的资料库（个人文档）中与查询相关的片段。

        当主题可能与用户已上传的资料相关、或用户希望基于自己的资料出题时优先使用；
        若返回“没有相关内容”或结果不相关，请改用联网搜索补充。
        """
        user_id = (config.get("configurable") or {}).get("user_id")
        if not user_id:
            return "（当前用户暂无可用资料库内容，请使用联网搜索）"
        try:
            hits = search_knowledge_base(int(user_id), query)
        except Exception as exc:  # noqa: BLE001 - 工具层降级为可读字符串，不向上抛
            logger.warning("资料库检索失败，降级为联网：%s", type(exc).__name__)
            return "（资料库暂时不可用，请改用联网搜索获取资料）"
        if not hits:
            return "（资料库中没有与该查询相关的内容，请使用联网搜索补充）"
        payload = [
            {
                "filename": hit.filename,
                "content": hit.text[:snippet_max],
                "score": round(1 - hit.distance, 3),
            }
            for hit in hits
        ]
        return json.dumps({"results": payload}, ensure_ascii=False)

    return kb_search


# ---- 结果解析（工具消息 → 摘要 / 来源 / 溯源） ----


def _parse_tool_content(content: Any) -> Optional[dict]:
    """解析工具消息内容为 dict；失败返回 None。

    langgraph ToolNode 会把 dict 输出 json.dumps 为字符串放入 content；
    错误消息（ToolException 文本）无法解析为 JSON，自然被跳过。
    """
    if isinstance(content, dict):
        return content
    text: Optional[str] = None
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):  # content blocks
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        if parts:
            text = "".join(parts)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_agent_result(result: Any, max_summary_chars: int) -> KnowledgeResult:
    """从 Agent 输出消息中解析：摘要 / 来源 / 溯源 / 有效内容标记。"""
    messages: list = []
    if isinstance(result, dict):
        messages = result.get("messages", []) or []
    elif isinstance(result, list):
        messages = result

    summary = ""
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    search_count = 0
    extract_count = 0
    library_search_count = 0
    library_hit_count = 0
    queries: list[str] = []
    doc_count = 0
    has_valid = False

    for msg in messages:
        msg_type = getattr(msg, "type", None)

        # 工具调用统计（AIMessage.tool_calls）
        for tool_call in getattr(msg, "tool_calls", None) or []:
            name = tool_call.get("name")
            args = tool_call.get("args") or {}
            if name in ("tavily_search_basic", "tavily_search_deep"):
                search_count += 1
                query = args.get("query")
                if isinstance(query, str) and query.strip():
                    queries.append(query.strip())
            elif name == "tavily_extract":
                extract_count += 1
            elif name == "kb_search":
                library_search_count += 1
                query = args.get("query")
                if isinstance(query, str) and query.strip():
                    queries.append(query.strip())

        # 工具执行结果（ToolMessage）
        if msg_type == "tool":
            parsed = _parse_tool_content(getattr(msg, "content", None))
            if parsed is None or "error" in parsed:
                continue
            results = parsed.get("results") or []
            if not isinstance(results, list):
                continue

            # 资料库检索结果：{filename, content, score}
            if getattr(msg, "name", "") == "kb_search":
                doc_count += len(results)
                library_hit_count += len(results)
                for item in results:
                    if not isinstance(item, dict):
                        continue
                    filename = item.get("filename")
                    if not filename:
                        continue
                    dedup_key = f"library:{filename}"
                    if dedup_key not in seen_urls:
                        seen_urls.add(dedup_key)
                        sources.append({"type": "library", "title": str(filename)})
                    content_text = item.get("content") or ""
                    if isinstance(content_text, str) and len(content_text) >= MIN_VALID_CONTENT_CHARS:
                        has_valid = True
                continue

            # 联网检索结果（tavily_*）：{url, title, content/raw_content}
            doc_count += len(results)
            for item in results:
                if not isinstance(item, dict):
                    continue
                url = item.get("url")
                if not url:
                    continue
                title = item.get("title") or url
                if url not in seen_urls:
                    seen_urls.add(url)
                    sources.append({"type": "web", "title": str(title), "url": str(url)})
                content_text = item.get("content") or item.get("raw_content") or ""
                if isinstance(content_text, str) and len(content_text) >= MIN_VALID_CONTENT_CHARS:
                    has_valid = True

        # 最终答复（最后一条 AI 文本作为结构化摘录）
        if msg_type == "ai":
            content = getattr(msg, "content", None)
            if isinstance(content, str) and content.strip():
                summary = content.strip()

    summary = summary[:max_summary_chars]
    trace = {
        "search_count": search_count,
        "extract_count": extract_count,
        "queries": queries,
        "doc_count": doc_count,
        "library_search_count": library_search_count,
        "library_hit_count": library_hit_count,
    }
    return KnowledgeResult(
        summary=summary,
        sources=sources[:MAX_SOURCES],
        trace=trace,
        has_valid_content=has_valid,
    )


# ---- 步骤回调（工具事件 → 任务步骤） ----


def _describe_tool_input(name: str, input_str: Any, inputs: Any) -> str:
    """工具开始：把调用参数转成可读描述。

    注意：Agent 路径下 on_tool_start 的 input_str 是 Python repr 字符串
    （如 "{'query': 'x'}"，单引号），json.loads 会失败 → 用 literal_eval 兜底。
    """
    data = inputs if isinstance(inputs, dict) else None
    if data is None and isinstance(input_str, dict):
        data = input_str
    if data is None and isinstance(input_str, str):
        try:
            parsed = json.loads(input_str)
        except (ValueError, TypeError):
            try:
                parsed = ast.literal_eval(input_str)
            except (ValueError, SyntaxError):
                parsed = None
        if isinstance(parsed, dict):
            data = parsed
    if isinstance(data, dict):
        if name == "tavily_extract":
            urls = data.get("urls")
            if isinstance(urls, list) and urls:
                return f"提取：{urls[0]}"
        query = data.get("query")
        if isinstance(query, str) and query.strip():
            return f"搜索词：{query.strip()}"
    return "正在获取资料"


def _describe_tool_output(output: Any) -> str:
    """工具结束：把执行结果转成可读描述。

    注意：Agent（ToolNode）路径下 on_tool_end 收到的是 ToolMessage（content 为
    json.dumps 后的字符串）→ 先取 .content 再解析；同时兼容原始 dict 与 JSON 字符串。
    """
    content = getattr(output, "content", output)
    parsed = content if isinstance(content, dict) else _parse_tool_content(content)
    if isinstance(parsed, dict):
        results = parsed.get("results")
        if isinstance(results, list):
            return f"获得 {len(results)} 条资料"
    return "未获得资料"


class _StepCallback(BaseCallbackHandler):
    """把工具级事件转成任务步骤；key 用 run_id，保证同一次调用可更新同一步骤。"""

    def __init__(self, on_step: StepCallback) -> None:
        self._on_step = on_step
        self._labels: dict[str, str] = {}

    def _key(self, kwargs: dict) -> str:
        return str(kwargs.get("run_id"))

    def on_tool_start(self, serialized: dict, input_str: str, **kwargs: Any) -> None:
        name = (serialized or {}).get("name", "")
        label = TOOL_STEP_LABELS.get(name, "获取资料")
        key = self._key(kwargs)
        self._labels[key] = label
        self._on_step(key, label, _describe_tool_input(name, input_str, kwargs.get("inputs")), "doing")

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        key = self._key(kwargs)
        label = self._labels.get(key, "获取资料")
        self._on_step(key, label, _describe_tool_output(output), "done")

    def on_tool_error(self, error: BaseException, **kwargs: Any) -> None:
        key = self._key(kwargs)
        label = self._labels.get(key, "获取资料")
        self._on_step(key, label, "调用失败（已自动降级）", "done")


# ---- 对外入口 ----


def is_enabled(user_id: int | None = None) -> bool:
    """知识获取是否启用：联网凭据已配置，或（百炼已配置且该用户有就绪文档）。"""
    settings = get_settings()
    if settings.tavily_api_key:
        return True
    return (
        bool(settings.dashscope_api_key)
        and user_id is not None
        and _user_has_ready_documents(int(user_id))
    )


def _user_has_ready_documents(user_id: int) -> bool:
    """用户是否有处理就绪的文档（资料库工具注入判断；查询失败按无资料库降级）。"""
    try:
        from app.services.doc_service import has_ready_documents

        return has_ready_documents(user_id)
    except Exception:  # noqa: BLE001 - 查询失败保守降级
        logger.warning("查询用户文档状态失败，按无资料库处理", exc_info=True)
        return False


def _empty_result() -> KnowledgeResult:
    return KnowledgeResult(
        trace={
            "search_count": 0,
            "extract_count": 0,
            "queries": [],
            "doc_count": 0,
            "library_search_count": 0,
            "library_hit_count": 0,
        }
    )


def acquire_knowledge(
    user_input: str,
    on_step: Optional[StepCallback] = None,
    user_id: Optional[int] = None,
) -> KnowledgeResult:
    """执行知识获取。任何失败（构建 / 超时 / 异常）都降级返回“无有效内容”，不抛异常。

    Args:
        user_input: 用户的学习内容（可能包含网址）
        on_step: 可选步骤回调（工具级事件实时上报）
        user_id: 当前用户（有就绪文档时注入资料库检索工具；None = 不带资料库）
    """
    settings = get_settings()
    tavily_enabled = bool(settings.tavily_api_key)
    kb_enabled = (
        bool(settings.dashscope_api_key)
        and user_id is not None
        and _user_has_ready_documents(int(user_id))
    )
    if not tavily_enabled and not kb_enabled:
        return _empty_result()  # 无可用渠道（联网未配置且无资料库），调用方走兼容模式

    try:
        agent = _build_agent(include_kb=kb_enabled)
    except Exception as exc:  # noqa: BLE001 - 构建失败一律降级
        logger.warning("知识获取 Agent 构建失败，按无资料降级：%s", exc)
        return _empty_result()

    callbacks = [_StepCallback(on_step)] if on_step else []

    def _run():
        return agent.invoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config={
                "callbacks": callbacks,
                "recursion_limit": AGENT_RECURSION_LIMIT,
                "configurable": {"user_id": user_id},
            },
        )

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(_run)
    try:
        result = future.result(timeout=settings.search_agent_timeout_seconds)
    except TimeoutError:
        # 已知限制：超时后放弃等待，后台线程自然结束（见 design.md 风险）
        executor.shutdown(wait=False)
        logger.warning(
            "知识获取 Agent 超时（>%ss），按无资料降级", settings.search_agent_timeout_seconds
        )
        return _empty_result()
    except Exception as exc:  # noqa: BLE001 - 执行失败一律降级
        executor.shutdown(wait=False)
        logger.warning("知识获取 Agent 执行失败，按无资料降级：%s", exc)
        return _empty_result()
    executor.shutdown(wait=False)

    return _parse_agent_result(result, settings.search_summary_max_chars)
