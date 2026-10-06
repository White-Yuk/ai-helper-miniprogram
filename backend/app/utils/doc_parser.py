"""文档解析：按文件类型选择 LangChain loader，输出全文与有效性检测。

对齐 design.md D3：
- PDF：PyPDFLoader（pypdf）；.docx：Docx2txtLoader（docx2txt）；
  .md：TextLoader（UTF-8，解码失败尝试 GBK 兜底一次）；
- loader 输出 Document 列表 → 拼接全文；
- 有效文本长度低于阈值（默认 20 字符）→ DocParseError（可读原因，如扫描版 PDF 无文本层）。
"""
from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader

# 有效文本阈值（低于此长度视为解析失败：如扫描版 PDF）
MIN_TEXT_CHARS = 20

# 支持的文件类型 → 扩展名
FILE_TYPES = {"pdf": ".pdf", "docx": ".docx", "md": ".md"}


class DocParseError(Exception):
    """文档解析失败（携带可读原因）。"""


def normalize_file_type(filename: str) -> str:
    """从文件名推断文件类型（pdf / docx / md）；不支持时返回空字符串。"""
    suffix = Path(filename).suffix.lower()
    for file_type, ext in FILE_TYPES.items():
        if suffix == ext:
            return file_type
    return ""


def parse_document(path: Path, file_type: str) -> str:
    """解析文档为纯文本全文；失败抛 DocParseError（可读原因）。"""
    if file_type not in FILE_TYPES:
        raise DocParseError(f"不支持的文件类型：{file_type}")

    try:
        if file_type == "pdf":
            docs = PyPDFLoader(str(path)).load()
        elif file_type == "docx":
            docs = Docx2txtLoader(str(path)).load()
        else:  # md
            try:
                docs = TextLoader(str(path), encoding="utf-8").load()
            except UnicodeDecodeError:
                docs = TextLoader(str(path), encoding="gbk").load()
    except Exception as exc:  # noqa: BLE001 - 统一转可读失败原因
        raise DocParseError(f"文档解析失败：{type(exc).__name__}") from exc

    parts = [
        doc.page_content.strip()
        for doc in docs
        if getattr(doc, "page_content", None) and doc.page_content.strip()
    ]
    text = "\n".join(parts).strip()
    if len(text) < MIN_TEXT_CHARS:
        raise DocParseError("未提取到有效文本（暂不支持扫描版 PDF）")
    return text
