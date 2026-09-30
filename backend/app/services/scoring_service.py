"""统计服务：正确率与得分摘要计算（数字由后端计算，不交给 LLM）。"""
from __future__ import annotations

from app.models.report import AnswerRecord


def compute_accuracy(records: list[AnswerRecord]) -> int:
    """计算正确率（0-100 的整数；无记录时返回 0）。"""
    if not records:
        return 0
    correct = sum(1 for record in records if record.is_correct)
    return round(correct / len(records) * 100)


def compute_score_summary(records: list[AnswerRecord]) -> dict:
    """汇总得分信息，用于报告 Prompt 与响应。"""
    total = len(records)
    correct = sum(1 for record in records if record.is_correct)
    return {
        "total": total,
        "correct": correct,
        "wrong": total - correct,
        "accuracy": compute_accuracy(records),
    }
