"""文档解析测试（add-rag-knowledge-base 任务 3.3）。

覆盖：类型推断 / md 解析 / docx 解析（最小合法 docx）/ PDF 解析（程序生成最小 PDF）/
有效文本阈值 / 不支持类型 / 文件缺失。

说明：测试样本由本文件程序化生成（无网络、无外部文件依赖）。
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.utils.doc_parser import DocParseError, normalize_file_type, parse_document


def _write_min_pdf(path: Path, text: str) -> None:
    """生成含一行文本的最小合法 PDF（无压缩、标准 xref）。"""
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"",  # 占位：内容流（依赖文本）
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    content = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode("latin-1")
    objects[3] = b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode()
    path.write_bytes(bytes(out))


def _write_min_docx(path: Path, text: str) -> None:
    """生成含一段文本的最小合法 docx（zip 包 + 必备 rels + document.xml）。"""
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/>'
        "</Relationships>"
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
        "</w:document>"
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document)


class TestNormalizeFileType:
    def test_supported(self):
        assert normalize_file_type("RAG 入门.pdf") == "pdf"
        assert normalize_file_type("资料.DOCX") == "docx"
        assert normalize_file_type("notes.md") == "md"

    def test_unsupported(self):
        assert normalize_file_type("notes.txt") == ""
        assert normalize_file_type("archive.zip") == ""
        assert normalize_file_type("noext") == ""


class TestParseDocument:
    def test_parse_md(self, tmp_path):
        target = tmp_path / "notes.md"
        target.write_text("# RAG 笔记\n\n检索增强生成的核心流程是先检索再生成。", encoding="utf-8")
        text = parse_document(target, "md")
        assert "检索增强生成的核心流程" in text

    def test_parse_docx(self, tmp_path):
        target = tmp_path / "notes.docx"
        _write_min_docx(target, "这是 docx 文档中的测试文本，长度足够通过有效性检查。")
        text = parse_document(target, "docx")
        assert "docx 文档中的测试文本" in text

    def test_parse_pdf(self, tmp_path):
        target = tmp_path / "notes.pdf"
        _write_min_pdf(target, "RAG basics test content for parsing")
        text = parse_document(target, "pdf")
        assert "RAG basics test" in text

    def test_too_short_text_fails(self, tmp_path):
        target = tmp_path / "short.md"
        target.write_text("太短", encoding="utf-8")
        with pytest.raises(DocParseError) as exc_info:
            parse_document(target, "md")
        assert "未提取到有效文本" in str(exc_info.value)

    def test_unsupported_type_fails(self, tmp_path):
        target = tmp_path / "notes.txt"
        target.write_text("x" * 50, encoding="utf-8")
        with pytest.raises(DocParseError):
            parse_document(target, "txt")

    def test_missing_file_fails(self, tmp_path):
        with pytest.raises(DocParseError):
            parse_document(tmp_path / "missing.pdf", "pdf")
