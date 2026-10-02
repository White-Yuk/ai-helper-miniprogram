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


# ---- 数据库测试夹具（阶段 1+） ----
# 说明：测试统一使用 SQLite 临时文件库（不依赖本机 MySQL，保证随时可跑）；
# 业务代码不写 MySQL 专属 SQL，真实库兼容性由 scripts/check_db.py 与联调验证。


@pytest.fixture()
def db_session(tmp_path):
    """独立的 SQLite 临时库会话（每个测试独享，自动销毁）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401  确保全部模型注册到 metadata
    from app.core.db import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client_db(app, db_session):
    """覆盖 get_db 依赖的 TestClient：API 测试走 SQLite 临时库。"""
    from app.core.db import get_db

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---- 登录相关测试夹具（阶段 1+） ----


@pytest.fixture()
def auth_settings(monkeypatch):
    """隔离登录相关配置（不读 .env 的真实值），并在测试后清理缓存。"""
    monkeypatch.setenv("AUTH_MOCK_ENABLED", "true")
    monkeypatch.setenv("JWT_SECRET", "test-secret-for-pytest-0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("JWT_EXPIRE_DAYS", "30")
    monkeypatch.setenv("WECHAT_APPID", "")
    monkeypatch.setenv("WECHAT_SECRET", "")

    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def login_headers(client, device_id: str = "device_default") -> dict[str, str]:
    """辅助：开发态模拟登录，返回可直接使用的 Authorization 头。

    使用前需先激活 auth_settings 夹具（test 文件里用 pytestmark = pytest.mark.usefixtures("auth_settings")）。
    """
    resp = client.post("/api/v1/auth/dev-login", json={"device_id": device_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0
    return {"Authorization": f"Bearer {body['data']['token']}"}


def login_user(client, device_id: str = "device_default") -> tuple[dict[str, str], int]:
    """辅助：登录并返回 (headers, user_id)。"""
    headers = login_headers(client, device_id)
    resp = client.get("/api/v1/me", headers=headers)
    assert resp.status_code == 200, resp.text
    return headers, resp.json()["data"]["id"]


# ---- 阶段 5-7 造数辅助（stats / mastery / wrongbook 测试共用） ----


def make_quiz_record(session, user_id: int, questions: list, **overrides):
    """直接构造一条已落库的闯关记录（绕过 LLM 链路）。"""
    import uuid
    from datetime import datetime

    from app.models.records import Quiz

    defaults = dict(
        quiz_id=f"quiz_t{uuid.uuid4().hex[:10]}",
        user_id=user_id,
        title="RAG 入门",
        summary="测试题库",
        source_type="text",
        questions=[q.model_dump() for q in questions],
        status="doing",
        current_index=0,
        completed_at=None,
    )
    defaults.update(overrides)
    quiz = Quiz(**defaults)
    session.add(quiz)
    session.commit()
    session.refresh(quiz)
    return quiz


def make_answer_record(session, quiz, user_id: int, question, is_correct: bool, **overrides):
    """直接构造一条作答明细。"""
    from app.models.records import Answer

    defaults = dict(
        quiz_id=quiz.quiz_id,
        user_id=user_id,
        question_id=question.id,
        question_type=question.type,
        knowledge_point=question.knowledge_point,
        selected_answers=question.answer if is_correct else ["Z"],
        is_correct=is_correct,
        duration_ms=1000,
    )
    defaults.update(overrides)
    answer = Answer(**defaults)
    session.add(answer)
    session.commit()
    return answer
