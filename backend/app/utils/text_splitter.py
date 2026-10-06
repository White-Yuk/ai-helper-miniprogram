"""文本分块工厂：LangChain RecursiveCharacterTextSplitter（参数来自配置）。

对齐 design.md D3：
- `length_function=len`：按字符计数（中文场景直观，与配置语义一致）；
- 分隔符策略：段间空行 → 换行 → 中文句读（。！？；）→ 英文句读 → 空格 → 字符兜底，
  对中文长段落先按句子切分，质量优于纯字符硬切。
"""
from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import get_settings

# 中文友好的分隔符序列（优先保证语义边界，最后退到字符级兜底）
CHINESE_FRIENDLY_SEPARATORS = [
    "\n\n",
    "\n",
    "。",
    "！",
    "？",
    "；",
    ".",
    "!",
    "?",
    ";",
    " ",
    "",
]


def build_text_splitter() -> RecursiveCharacterTextSplitter:
    """构建分块器（每次调用新实例；无状态）。"""
    settings = get_settings()
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.kb_chunk_size,
        chunk_overlap=settings.kb_chunk_overlap,
        length_function=len,
        is_separator_regex=False,
        separators=CHINESE_FRIENDLY_SEPARATORS,
    )
