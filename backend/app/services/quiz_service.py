"""出题服务：调用出题链 + 五级校验兜底 + 自动重试。

可靠性设计（对齐方案设计文档 7.4）：
1. 一级：模型返回为空 / 无法解析 -> 可重试错误
2. 二级：结构化输出映射失败（LangChain 抛异常）-> 可重试错误
3. 三级：业务字段完整性校验（validate_quiz_quality）-> 可重试错误
4. 四级：自动重试（次数 = settings.llm_max_retries）
5. 五级：全部失败 -> 抛 BizException(4001)，由全局处理器返回友好错误
"""
from __future__ import annotations

import logging

from app.core.config import get_settings
from app.core.exceptions import BizException
from app.models.quiz import QuizData, QuizGenerateData, QuizGenerateRequest
from app.prompts.quiz_prompt import DIFFICULTY_CN, build_types_requirement
from app.utils.id_generator import new_quiz_id
from app.utils.text_cleaner import clean_input

logger = logging.getLogger(__name__)


class QuizValidationError(ValueError):
    """题库结构校验失败（可重试）。"""


def validate_quiz_quality(data: QuizData, request: QuizGenerateRequest) -> None:
    """题库业务校验：数量、题型匹配、选项与答案一致性。

    校验失败抛 QuizValidationError，由上层触发重试。
    """
    # 1. 题目数量必须与请求一致
    if len(data.questions) != request.question_count:
        raise QuizValidationError(f"题目数量不符：期望 {request.question_count} 题，实际 {len(data.questions)} 题")

    # 2. 题型集合：既不能缺、也不能多
    got_types = {q.type for q in data.questions}
    requested_types = set(request.question_types)
    missing = requested_types - got_types
    if missing:
        raise QuizValidationError(f"缺少请求的题型：{sorted(missing)}")
    unexpected = got_types - requested_types
    if unexpected:
        raise QuizValidationError(f"出现未请求的题型：{sorted(unexpected)}")

    # 3. 逐题结构校验
    seen_ids: set[str] = set()
    for q in data.questions:
        if q.id in seen_ids:
            raise QuizValidationError(f"题目 id 重复：{q.id}")
        seen_ids.add(q.id)

        option_keys = {option.key for option in q.options}
        if q.type == "single":
            if len(q.options) < 2:
                raise QuizValidationError(f"单选题选项不足（{q.id}）")
            if len(q.answer) != 1:
                raise QuizValidationError(f"单选题只能有 1 个答案（{q.id}）")
            if q.answer[0] not in option_keys:
                raise QuizValidationError(f"单选题答案不在选项中（{q.id}）")
        elif q.type == "multiple":
            if len(q.options) < 3:
                raise QuizValidationError(f"多选题选项不足（{q.id}）")
            if len(q.answer) < 2:
                raise QuizValidationError(f"多选题至少需要 2 个答案（{q.id}）")
            if not set(q.answer) <= option_keys:
                raise QuizValidationError(f"多选题答案不在选项中（{q.id}）")
        elif q.type == "judge":
            # 答案格式已由 Question 模型保证为 ["对"] 或 ["错"]
            pass
        elif q.type == "fill":
            blank_count = q.stem.count("____")
            if blank_count != len(q.answer):
                raise QuizValidationError(
                    f"填空题空位数量与答案数量不一致（{q.id}）：空位 {blank_count} 个，答案 {len(q.answer)} 个"
                )


def generate_quiz(request: QuizGenerateRequest, chain) -> QuizGenerateData:
    """生成题库：调用链 -> 校验 -> 失败重试 -> 兜底异常。

    Args:
        request: 已通过 Pydantic 校验的请求
        chain: 出题链（LCEL Runnable），invoke 输入为模板变量字典，输出 QuizData
    """
    settings = get_settings()
    inputs = {
        "user_input": clean_input(request.user_input),
        "question_count": str(request.question_count),
        "difficulty": DIFFICULTY_CN[request.difficulty],
        "types_requirement": build_types_requirement(request.question_types),
    }

    max_attempts = settings.llm_max_retries + 1
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            data = chain.invoke(inputs)
            if not isinstance(data, QuizData):
                raise QuizValidationError("模型输出结构无法解析为题库")
            validate_quiz_quality(data, request)
            return QuizGenerateData(
                quiz_id=new_quiz_id(),
                title=data.title,
                summary=data.summary,
                questions=data.questions,
            )
        except QuizValidationError as exc:
            last_error = exc
            logger.warning("题库校验失败（第 %s/%s 次尝试）：%s", attempt, max_attempts, exc)
        except Exception as exc:  # noqa: BLE001 - 模型/网络异常统一进入重试
            last_error = exc
            logger.warning("题库生成异常（第 %s/%s 次尝试）：%s", attempt, max_attempts, exc)

    logger.error("题库生成最终失败：%s", last_error)
    raise BizException(code=4001, message="题库生成失败，请稍后重试", http_status=502)
