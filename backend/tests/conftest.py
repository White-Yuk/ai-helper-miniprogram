"""公共测试夹具：应用实例、TestClient、Mock Chain 与样例数据。

原则：所有测试不触碰真实 LLM —— 通过 FakeChain 注入，保证离线可跑、不消耗 API 额度。
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models.quiz import Option, Question, QuizData


def make_question(qid: str = "q1", qtype: str = "single", **overrides) -> Question:
    """构造一道合规题目；通过 qtype 生成不同题型的默认值，可用 overrides 覆写。"""
    defaults: dict = dict(
        id=qid,
        type=qtype,
        stem="RAG 主要解决大模型的什么问题？",
        options=[Option(key="A", text="知识过时、容易“胡说”"), Option(key="B", text="推理速度太慢")],
        answer=["A"],
        explanation="测试讲解：大模型知识有截止日期，RAG 通过检索补充最新信息。",
        knowledge_point="核心概念",
        difficulty="easy",
    )
    if qtype == "multiple":
        defaults.update(
            stem="下列哪些属于 RAG 的典型应用场景？",
            options=[Option(key="A", text="企业私有知识问答"), Option(key="B", text="客服机器人"), Option(key="C", text="手机时钟界面")],
            answer=["A", "B"],
        )
    elif qtype == "judge":
        defaults.update(stem="判断题：RAG 的答案质量只取决于大模型本身。", options=[], answer=["错"])
    elif qtype == "fill":
        defaults.update(stem="RAG 的核心流程是先『____』再生成答案。", options=[], answer=["检索"])
    defaults.update(overrides)
    return Question(**defaults)


@pytest.fixture
def sample_questions() -> list[Question]:
    return [
        make_question("q1", "single"),
        make_question("q2", "multiple"),
        make_question("q3", "judge"),
        make_question("q4", "fill"),
    ]


@pytest.fixture
def sample_quiz_data(sample_questions: list[Question]) -> QuizData:
    return QuizData(title="RAG 入门", summary="围绕 RAG 基础概念生成的测试题库", questions=sample_questions)


class FakeChain:
    """模拟 LangChain Runnable 的 invoke 行为。

    script 为按调用顺序播放的脚本，每个元素可以是：
      - 返回值（正常返回）
      - Exception 实例（抛出该异常）
    超出脚本长度后重复使用最后一个元素。
    """

    def __init__(self, script: list):
        assert script, "script 不能为空"
        self.script = list(script)
        self.calls: list = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def invoke(self, inputs):  # noqa: ANN001
        self.calls.append(inputs)
        item = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c
