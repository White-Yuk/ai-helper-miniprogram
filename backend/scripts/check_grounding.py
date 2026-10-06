"""知识获取 + 出题 端到端联调检查（tasks 9.2）。

用法（在 backend 目录下执行）：
    # 阶段一：跑一次真实生成任务（真实 Tavily + 真实 DeepSeek），轮询到终态并输出证据
    .venv/Scripts/python.exe scripts/check_grounding.py
    .venv/Scripts/python.exe scripts/check_grounding.py --input "https://en.wikipedia.org/wiki/Prompt_engineering"

    # 阶段二：重开进程查询既有任务（验证「服务重启后仍可查询」的持久化）
    .venv/Scripts/python.exe scripts/check_grounding.py --query task_xxxxxxxxxxxx

说明：
- 真实调用外部 API 并产生费用（Tavily credits + DeepSeek 调用），不属于 tests/ 单测套件；
- 走完整任务流水线（generation_tasks 表 → 线程池执行 → 轮询查询），输出自动脱敏（不打印 Key）。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_DIR / ".env"

# 保证以任意 CWD 运行脚本时，均能加载 backend/.env 并导入 app 包
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

# Windows 控制台默认 GBK，遇到特殊字符会抛 UnicodeEncodeError → 统一切到 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001 - 极老终端不支持 reconfigure 时忽略
    pass

POLL_TIMEOUT_SECONDS = 300
POLL_INTERVAL_SECONDS = 2


def load_api_key() -> str:
    """从 backend/.env 读取 TAVILY_API_KEY（不打印内容）。"""
    if not ENV_PATH.exists():
        print(f"[FAIL] 未找到 {ENV_PATH}，请先从 .env.example 复制并填写配置")
        return ""
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=False)
    return os.getenv("TAVILY_API_KEY", "").strip()


def _safe_message(exc: Exception, api_key: str) -> str:
    message = f"{type(exc).__name__}: {exc}"
    if api_key:
        message = message.replace(api_key, "***")
    return message[:300]


def _print_steps(steps: list[dict]) -> None:
    print("    步骤轨迹：")
    for step in steps:
        print(f"      - [{step.get('state', '?')}] {step.get('label', '')}：{step.get('detail', '')}")


def _print_result(result: dict) -> None:
    trace = result.get("agent_trace") or {}
    sources = result.get("sources") or []
    questions = result.get("questions") or []
    print(
        f"[4] 知识溯源：检索 {trace.get('search_count', 0)} 次 / "
        f"提取 {trace.get('extract_count', 0)} 次 / 资料 {trace.get('doc_count', 0)} 条"
    )
    if trace.get("queries"):
        print(f"    查询词：{trace.get('queries')}")
    print(f"[5] 来源 {len(sources)} 条（前 5）：")
    for item in sources[:5]:
        print(f"      - {str(item.get('title', ''))[:60]} | {str(item.get('url', ''))[:80]}")
    print(f"[6] 题目抽样（共 {len(questions)} 题）：")
    for question in questions[:3]:
        print(f"      - [{question.get('type')}] {str(question.get('stem', ''))[:80]}")


def run_new_task(input_text: str, question_count: int, api_key: str) -> int:
    from app.models.quiz import QuizGenerateRequest
    from app.services import task_service

    print("=" * 58)
    print("阶段一：真实生成任务（端到端）")
    print("=" * 58)

    request = QuizGenerateRequest(user_input=input_text, question_count=question_count)
    session = task_service.get_session_factory()()
    try:
        task = task_service.create_task(session, request, user_id=None)
    finally:
        session.close()
    task_id = task.task_id
    print(f"[1] 任务已创建：{task_id}")
    task_service.submit_task(task_id)
    print("[2] 已提交后台执行，开始轮询……")

    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    status, steps, result, code, message = "pending", [], None, None, None
    last_status = ""
    while time.monotonic() < deadline:
        session = task_service.get_session_factory()()
        try:
            current = task_service.get_task(session, task_id, None)
            status = current.status
            steps = list(current.steps or [])
            result = current.result
            code, message = current.error_code, current.error_message
        finally:
            session.close()
        if status != last_status:
            print(f"    状态：{status}")
            last_status = status
        if status in ("done", "failed"):
            break
        time.sleep(POLL_INTERVAL_SECONDS)
    else:
        print("[FAIL] 轮询超时（5 分钟），任务仍未到终态")
        return 1

    print(f"[3] 最终状态：{status}")
    _print_steps(steps)

    if status == "failed":
        print(f"[FAIL] 任务失败：error_code={code} message={message}")
        return 1
    if result is None:
        print("[FAIL] 任务完成但结果为空（异常）")
        return 1

    _print_result(result)
    print(f"[7] 持久化验证：请重开一个终端执行以下命令（模拟服务重启后查询）：")
    print(f"    .venv/Scripts/python.exe scripts/check_grounding.py --query {task_id}")
    return 0


def run_query(task_id: str, api_key: str) -> int:
    from app.services import task_service

    print("=" * 58)
    print("阶段二：查询既有任务（验证持久化）")
    print("=" * 58)

    session = task_service.get_session_factory()()
    try:
        task = task_service.get_task(session, task_id, None)
        print(f"[1] 任务存在：{task.task_id}")
        print(f"[2] 状态：{task.status}（finished_at={task.finished_at}）")
        _print_steps(list(task.steps or []))
        if task.result is not None:
            title = task.result.get("title")
            questions = task.result.get("questions") or []
            print(f"[3] 结果仍可取回：title={title}，题目 {len(questions)} 题")
            for question in questions[:3]:
                print(f"      - [{question.get('type')}] {str(question.get('stem', ''))[:80]}")
        if task.error_code is not None:
            print(f"[4] 错误信息：code={task.error_code} message={task.error_message}")
    except Exception as exc:  # noqa: BLE001 - 检查脚本打印全部失败原因
        print(f"[FAIL] 查询失败：{_safe_message(exc, api_key)}")
        return 1
    finally:
        session.close()
    print("[PASS] 持久化验证通过：重启进程后任务状态与结果仍可查询")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="知识获取 + 出题端到端联调检查")
    parser.add_argument("--input", default="Harness Engineering", help="学习内容（默认 Harness Engineering）")
    parser.add_argument("--count", type=int, default=3, help="题目数量 3-10（默认 3，联调尽量省费用）")
    parser.add_argument("--query", default="", help="查询既有任务（验证持久化；传 task_xxx）")
    args = parser.parse_args()

    api_key = load_api_key()
    if not api_key:
        print("[FAIL] .env 中未配置 TAVILY_API_KEY（或为空）")
        print("       未配置时后端为兼容模式（纯模型出题），本联调脚本需要真实检索能力")
        return 1
    print(f"[0] TAVILY_API_KEY 已配置（以 tvly- 开头：{'是' if api_key.startswith('tvly-') else '否'}）；")
    print("    注意：本次联调会真实调用 Tavily 与 DeepSeek（产生少量费用）")

    try:
        if args.query:
            return run_query(args.query, api_key)
        return run_new_task(args.input, args.count, api_key)
    except Exception as exc:  # noqa: BLE001 - 顶层兜底，保证脚本可读报错
        print(f"[FAIL] 执行异常：{_safe_message(exc, api_key)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
