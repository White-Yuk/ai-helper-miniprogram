"""分块器测试（add-rag-knowledge-base 任务 3.2）。

覆盖：参数来自配置 / 中文段落切分 / 超长单段硬切 / 重叠行为 / 空输入。
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.utils.text_splitter import build_text_splitter


@pytest.fixture
def patch_settings(monkeypatch):
    def _apply(chunk_size: int = 500, chunk_overlap: int = 50):
        settings = SimpleNamespace(kb_chunk_size=chunk_size, kb_chunk_overlap=chunk_overlap)
        monkeypatch.setattr("app.utils.text_splitter.get_settings", lambda: settings)

    return _apply


class TestBuildTextSplitter:
    def test_parameters_from_settings(self, patch_settings):
        patch_settings(chunk_size=100, chunk_overlap=10)
        splitter = build_text_splitter()
        assert splitter._chunk_size == 100
        assert splitter._chunk_overlap == 10

    def test_chinese_paragraphs_split(self, patch_settings):
        patch_settings(chunk_size=60, chunk_overlap=0)
        splitter = build_text_splitter()
        text = (
            "第一段：RAG 是检索增强生成，先检索再生成。第一段的后半部分也写在这里凑一点长度。"
            "\n\n"
            "第二段：向量数据库用于存储嵌入向量。"
        )
        chunks = splitter.split_text(text)
        assert len(chunks) >= 2
        assert all(len(chunk) <= 60 for chunk in chunks)
        joined = "".join(chunks)
        assert "RAG 是检索增强生成" in joined
        assert "第二段" in joined

    def test_long_single_paragraph_hard_split(self, patch_settings):
        patch_settings(chunk_size=50, chunk_overlap=0)
        splitter = build_text_splitter()
        text = "很长的句子" * 30  # 150 字符，无任何分隔符
        chunks = splitter.split_text(text)
        assert len(chunks) >= 3
        assert all(len(chunk) <= 50 for chunk in chunks)
        assert "".join(chunks) == text  # 无重叠时内容应完全保留

    def test_overlap_duplicates_content(self, patch_settings):
        patch_settings(chunk_size=30, chunk_overlap=10)
        splitter = build_text_splitter()
        text = "0123456789" * 6  # 60 字符
        chunks = splitter.split_text(text)
        assert len(chunks) >= 2
        # 存在重叠 → 各块长度之和大于原文长度
        assert sum(len(chunk) for chunk in chunks) > len(text)

    def test_empty_text(self, patch_settings):
        patch_settings()
        splitter = build_text_splitter()
        assert splitter.split_text("") == []
