"""出题链构建测试：结构化输出绑定（function_calling 主路径 / json_mode 异构兜底）。"""
from __future__ import annotations

from app.llm.quiz_chain import build_quiz_chain


def _find_binding_kwargs(runnable) -> dict | None:
    """递归查找 LangChain 模型绑定层（携带结构化输出配置），返回其 kwargs。"""
    stack = [runnable]
    while stack:
        node = stack.pop()
        kwargs = getattr(node, "kwargs", None)
        if isinstance(kwargs, dict) and ("tools" in kwargs or "response_format" in kwargs):
            return kwargs
        for attr in ("steps", "bound"):
            child = getattr(node, attr, None)
            if child is None:
                continue
            stack.extend(child if isinstance(child, (list, tuple)) else [child])
    return None


class TestBuildQuizChain:
    def test_default_chain_binds_quizdata_tool(self):
        chain = build_quiz_chain()
        kwargs = _find_binding_kwargs(chain)

        assert kwargs is not None
        assert kwargs["tools"][0]["function"]["name"] == "QuizData"
        # 事实记录：LangChain 1.6.6 的 function_calling 模式默认已绑定
        # tool_choice 指定 QuizData（即空响应为服务端无视约束所致，重复加强约束无意义）
        assert kwargs.get("tool_choice") == {"type": "function", "function": {"name": "QuizData"}}

    def test_json_mode_chain_uses_response_format(self):
        chain = build_quiz_chain(structured_method="json_mode")
        kwargs = _find_binding_kwargs(chain)

        assert kwargs is not None
        assert kwargs["response_format"]["type"] == "json_object"
        assert "tools" not in kwargs  # 异构路径：不走工具调用管线
