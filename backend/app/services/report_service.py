"""报告服务：后端统计正确率 + LLM 生成文字分析 + 重试兜底。"""
from __future__ import annotations

import json
import logging

from app.core.config import get_settings
from app.core.exceptions import BizException
from app.models.report import AnswerRecord, ReportData, ReportGenerateRequest, ReportLlmOutput
from app.models.quiz import Question
from app.services.scoring_service import compute_score_summary

logger = logging.getLogger(__name__)


def _dump_questions(questions: list[Question]) -> str:
    """题库序列化为紧凑 JSON（供模型阅读）。"""
    payload = [q.model_dump() for q in questions]
    return json.dumps(payload, ensure_ascii=False)


def _dump_records(records: list[AnswerRecord]) -> str:
    payload = [r.model_dump() for r in records]
    return json.dumps(payload, ensure_ascii=False)


def generate_report(request: ReportGenerateRequest, chain) -> ReportData:
    """生成复盘报告：统计（后端） + 文字分析（LLM）。

    Args:
        request: 报告请求（题库 + 作答记录）
        chain: 报告链，invoke 输入为模板变量字典，输出 ReportLlmOutput
    """
    settings = get_settings()
    summary = compute_score_summary(request.answer_records)
    score_text = (
        f"总题数 {summary['total']} · 答对 {summary['correct']} · "
        f"答错 {summary['wrong']} · 正确率 {summary['accuracy']}%"
    )

    inputs = {
        "topic": request.topic,
        "quiz_json": _dump_questions(request.questions),
        "answer_records": _dump_records(request.answer_records),
        "score_summary": score_text,
    }

    max_attempts = settings.llm_max_retries + 1
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            output = chain.invoke(inputs)
            if not isinstance(output, ReportLlmOutput):
                raise ValueError("模型输出结构无法解析为报告")
            return ReportData(accuracy=summary["accuracy"], **output.model_dump())
        except Exception as exc:  # noqa: BLE001 - 统一重试
            last_error = exc
            logger.warning("报告生成异常（第 %s/%s 次尝试）：%s", attempt, max_attempts, exc)

    logger.error("报告生成最终失败：%s", last_error)
    raise BizException(code=4002, message="复盘报告生成失败，请稍后重试", http_status=502)
