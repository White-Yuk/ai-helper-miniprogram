"""前置验证 T1：create_agent 运行时 config → 工具的传播（资料库检索的关键机制）。

验证目标（对齐 add-rag-knowledge-base design.md D5）：
- `create_agent(...).invoke(..., config={"configurable": {"user_id": ...}})` 时，
  工具函数（带 `RunnableConfig` 参数）能读到同一个 user_id；
- 该机制是「资料库检索工具按用户隔离」的关键依赖；
- `RunnableConfig` 参数不会暴露给 LLM（args_schema 只含业务参数）。

用法（backend 目录）：
    .venv/Scripts/python.exe scripts/check_agent_tool_config.py

说明：使用脚本化假 LLM（不触网、不消耗额度）；不属于 tests/ 单元测试套件。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


class ScriptedFakeChatModel(BaseChatModel):
    """按脚本返回预设 AIMessage 序列的假模型（离线驱动 Agent 走完工具调用轮次）。"""

    responses: list
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-fake"

    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN201 - 测试用，忽略绑定
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: ANN001
        index = min(self.calls, len(self.responses) - 1)
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=self.responses[index])])


captured_user_ids: list = []


@tool
def kb_search(query: str, config: RunnableConfig) -> str:
    """检索当前用户资料库中与 query 相关的片段（T1 验证用）。"""
    user_id = config.get("configurable", {}).get("user_id")
    captured_user_ids.append(user_id)
    return f"命中 user_id={user_id} 的资料：关于 {query} 的片段"


def main() -> int:
    print("=" * 52)
    print("T1 验证：create_agent 运行时 config → 工具的传播")
    print("=" * 52)

    schema_properties = list(kb_search.args_schema.model_json_schema().get("properties", {}).keys())
    print(f"[0] 工具 args_schema 参数：{schema_properties}（应只有 query，无 config）")
    if schema_properties != ["query"]:
        print("    [WARN] config 参数疑似暴露给 LLM")

    def build(query: str, call_id: str):
        fake = ScriptedFakeChatModel(
            responses=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "kb_search", "args": {"query": query}, "id": call_id}],
                ),
                AIMessage(content="基于命中的资料完成回答。"),
            ]
        )
        return create_agent(fake, tools=[kb_search], system_prompt="你是测试助手。")

    # 第一次调用：user_id=42
    agent = build("RAG 流程", "call_1")
    agent.invoke(
        {"messages": [{"role": "user", "content": "请检索我的资料"}]},
        config={"configurable": {"user_id": 42}},
    )
    print(f"[1] 第一次调用（user_id=42）工具捕获：{captured_user_ids}")

    ok = captured_user_ids == [42]
    if ok:
        # 第二次调用：user_id=7（验证逐次传递、互不串扰）
        captured_user_ids.clear()
        agent2 = build("别的主题", "call_2")
        agent2.invoke(
            {"messages": [{"role": "user", "content": "再查一次"}]},
            config={"configurable": {"user_id": 7}},
        )
        print(f"[2] 第二次调用（user_id=7）工具捕获：{captured_user_ids}")
        ok = captured_user_ids == [7]
        print(f"[3] 断言：{'通过 ✓ user_id 逐次正确传播到工具' if ok else '失败 ✗ 第二次不一致'}")
    else:
        print("[3] 断言失败 ✗：config 未传播到工具 → 需改用 contextvars 备选方案并更新 design.md")

    print("-" * 52)
    print("结论：T1 " + ("通过（design D5 的 config 注入机制可用）" if ok else "未通过（需切换备选方案）"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
