"""Embedding 工厂测试（add-rag-knowledge-base 任务 3.1）。

约定：不触网——仅断言构造参数与未配置行为，不发起真实请求。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm.embedding import (
    EmbeddingNotConfiguredError,
    build_embeddings,
    is_embedding_enabled,
)


def _fake_settings(**overrides) -> SimpleNamespace:
    base = dict(
        dashscope_api_key="sk-unit-test",
        dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        embedding_model="text-embedding-v4",
        embedding_dimensions=1024,
        embedding_batch_size=10,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def patch_settings(monkeypatch):
    def _apply(**overrides):
        settings = _fake_settings(**overrides)
        monkeypatch.setattr("app.llm.embedding.get_settings", lambda: settings)
        return settings

    return _apply


class TestBuildEmbeddings:
    def test_configured_parameters(self, patch_settings):
        patch_settings()
        embeddings = build_embeddings()
        assert embeddings.model == "text-embedding-v4"
        assert embeddings.dimensions == 1024
        assert embeddings.check_embedding_ctx_length is False
        assert embeddings.chunk_size == 10
        assert getattr(embeddings, "openai_api_base", "") == "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def test_custom_values_passed_through(self, patch_settings):
        patch_settings(embedding_dimensions=768, embedding_batch_size=5)
        embeddings = build_embeddings()
        assert embeddings.dimensions == 768
        assert embeddings.chunk_size == 5

    def test_not_configured_raises(self, patch_settings):
        patch_settings(dashscope_api_key="")
        with pytest.raises(EmbeddingNotConfiguredError):
            build_embeddings()


class TestIsEmbeddingEnabled:
    def test_enabled(self, patch_settings):
        patch_settings()
        assert is_embedding_enabled() is True

    def test_disabled(self, patch_settings):
        patch_settings(dashscope_api_key="")
        assert is_embedding_enabled() is False
