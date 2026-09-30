"""文本清洗工具。"""
from __future__ import annotations

import re


def clean_input(text: str) -> str:
    """清洗用户输入：统一空白字符、折叠多余空行，保留段落结构。"""
    text = text.replace("\u3000", " ")  # 全角空格 -> 半角
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\t ]+", " ", text)  # 连续空格/制表符折叠
    text = re.sub(r"\n{3,}", "\n\n", text)  # 3 个以上换行折叠为 2 个
    return text.strip()
