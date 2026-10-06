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
from app.llm.assessor import assess_reliability
from app.models.quiz import AgentTrace, QuizData, QuizGenerateData, QuizGenerateRequest, QuizSource
from app.prompts.quiz_prompt import DIFFICULTY_CN, NO_REFERENCE_CONTEXT, build_types_requirement
from app.services.knowledge_agent import StepCallback, acquire_knowledge, is_enabled
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


def generate_quiz(
    request: QuizGenerateRequest,
    chain,
    reference_context: str | None = None,
) -> QuizGenerateData:
    """生成题库：调用链 -> 校验 -> 失败重试 -> 兜底异常。

    Args:
        request: 已通过 Pydantic 校验的请求
        chain: 出题链（LCEL Runnable），invoke 输入为模板变量字典，输出 QuizData
        reference_context: 参考资料（知识获取摘要）；无资料传 None（自动用固定占位提示）
    """
    settings = get_settings()
    inputs = {
        "user_input": clean_input(request.user_input),
        "reference_context": reference_context or NO_REFERENCE_CONTEXT,
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


# 知识盲区提示（4006）：任务以失败状态携带，客户端展示专用引导
KNOWLEDGE_BLIND_SPOT_MESSAGE = (
    "这个主题暂时缺少可靠资料，为避免出错，先不生成题库。"
    "可以补充一段介绍、粘贴相关链接，或换个主题试试。"
)


def _emit_step(on_step: StepCallback | None, key: str, label: str, detail: str, state: str) -> None:
    if on_step is not None:
        on_step(key, label, detail, state)


def generate_quiz_with_grounding(
    request: QuizGenerateRequest,
    chain,
    on_step: StepCallback | None = None,
) -> QuizGenerateData:
    """带知识获取的编排：Agent 获取资料 → 有效内容判定 → （守卫）→ 出题 → 组装产物。

    行为矩阵（design D7）：
    - 未配置 key：与升级前行为完全一致（纯模型知识出题，不产生来源 / 轨迹）；
    - 已配置 + 有有效内容：资料作为 reference_context 注入出题链；携带 sources / agent_trace；
    - 已配置 + 无有效内容：评估知识可靠性——可靠 → 纯模型出题；不可靠 → BizException(4006)；
      评估失败 → 降级为纯模型出题（等价升级前行为）；
    - 检索失败 / 超时不会导致任务失败（Agent 层已降级为空结果）。

    Args:
        request: 生成请求
        chain: 出题链（测试 / 路由通过依赖注入替换）
        on_step: 可选步骤回调（阶段步骤：研判 / 出题 / 完成；工具级步骤由 Agent 回调产生）
    """
    sources: list[QuizSource] | None = None
    agent_trace: AgentTrace | None = None
    reference_context: str | None = None

    if is_enabled():
        knowledge = acquire_knowledge(clean_input(request.user_input), on_step)
        trace = AgentTrace(**knowledge.trace) if knowledge.trace else AgentTrace()
        has_activity = bool(trace.search_count or trace.extract_count)

        if knowledge.has_valid_content:
            reference_context = knowledge.summary or None
            sources = [QuizSource(**item) for item in knowledge.sources]
            agent_trace = trace
            _emit_step(
                on_step, "stage:judge", "资料研判", f"已获取 {trace.doc_count} 条资料，将据此出题", "done"
            )
        else:
            _emit_step(on_step, "stage:judge", "资料研判", "未获取到有效资料，正在评估主题可靠性", "doing")
            assessment = None
            try:
                assessment = assess_reliability(clean_input(request.user_input))
            except Exception as exc:  # noqa: BLE001 - 评估失败降级为纯模型出题
                logger.warning("知识可靠性评估失败，降级为纯模型出题：%s", exc)

            if assessment is not None and not assessment.reliable:
                _emit_step(on_step, "stage:judge", "资料研判", f"判定为知识盲区：{assessment.reason}", "done")
                raise BizException(code=4006, message=KNOWLEDGE_BLIND_SPOT_MESSAGE, http_status=502)

            detail = "评估通过：基于模型既有知识出题" if assessment else "评估不可用：降级为纯模型出题"
            _emit_step(on_step, "stage:judge", "资料研判", detail, "done")
            sources = []
            agent_trace = trace if has_activity else None

    _emit_step(on_step, "stage:generate", "AI 出题", "正在生成题目", "doing")
    data = generate_quiz(request, chain, reference_context=reference_context)
    _emit_step(on_step, "stage:generate", "AI 出题", "题目生成完成", "done")
    _emit_step(on_step, "stage:finish", "完成", "组卷完成，准备进入闯关", "done")

    data.sources = sources
    data.agent_trace = agent_trace
    return data
