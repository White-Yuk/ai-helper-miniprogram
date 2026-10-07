"""出题批量基准测试脚本（成功率 + 耗时统计）。

用途：对「AI 出题」完整链路做批量真实测试，产出可复现的成功 / 失败 / 耗时数据，
用于项目数据统计（如简历、项目报告）。

测试口径（与小程序端完全一致的链路与参数）：
- 链路：task_service.create_task → submit_task → 轮询 get_task（异步任务流水线）；
- 参数：5 题 / mixed 难度 / 单选 + 多选 + 判断（产品默认）；
- 用例：500 条 = 100 个主题 × 5 种自然语言输入句式，按主题轮换分配为两个子集：
    * mode=model ：300 条（不检索，纯模型知识出题；进程内禁用 Tavily，兼容模式）；
    * mode=search：200 条（联网检索 + 出题；Agent 按需选择轻快 / 深度档）。
  两个子集均覆盖全部主题与句式（每个主题 3 条 model + 2 条 search，均衡可比）；
- 并发：通过环境变量按脚本进程覆盖（默认 5），不影响 .env 与其他服务；
- 记录：每条完成即增量写入 JSONL（可中断续跑），记录成功 / 失败与耗时。

用法（在 backend 目录下执行；两种模式必须分两次运行，避免进程内模式竞态）：
    # 试跑
    .venv/Scripts/python.exe scripts/bench_quiz_generation.py --mode model  --total 10 --result scripts/results/smoke_model.jsonl
    .venv/Scripts/python.exe scripts/bench_quiz_generation.py --mode search --total 10 --result scripts/results/smoke_search.jsonl

    # 正式跑（两次运行）
    .venv/Scripts/python.exe scripts/bench_quiz_generation.py --mode model  --result scripts/results/bench_model_300.jsonl
    .venv/Scripts/python.exe scripts/bench_quiz_generation.py --mode search --result scripts/results/bench_search_200.jsonl

    # 合并统计两个结果文件（逗号分隔多个路径），输出总报告 + 分模式报告
    .venv/Scripts/python.exe scripts/bench_quiz_generation.py --stats-only --result scripts/results/bench_model_300.jsonl,scripts/results/bench_search_200.jsonl

说明：真实调用 DeepSeek（以及 search 模式下的 Tavily，产生费用）；不属于 tests/ 单测套件。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import Counter, deque
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = BACKEND_DIR / "scripts" / "results"

# 保证以任意 CWD 运行脚本时，均能加载 backend/.env 并导入 app 包
os.chdir(BACKEND_DIR)
sys.path.insert(0, str(BACKEND_DIR))

# Windows 控制台默认 GBK，遇到特殊字符会抛 UnicodeEncodeError → 统一切到 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001 - 极老终端不支持 reconfigure 时忽略
    pass

# 产品默认出题参数（对齐 QuizGenerateRequest 默认值）
QUESTION_COUNT = 5
DIFFICULTY = "mixed"
QUESTION_TYPES = ["single", "multiple", "judge"]

# ---- 100 个测试主题（10 个类目 × 10~15 个主题） ----
TOPICS: list[tuple[str, str]] = [
    # AI 与机器学习（12）
    ("AI与机器学习", "RAG 检索增强生成"),
    ("AI与机器学习", "Transformer 注意力机制"),
    ("AI与机器学习", "大语言模型的提示工程"),
    ("AI与机器学习", "机器学习中的过拟合"),
    ("AI与机器学习", "决策树算法原理"),
    ("AI与机器学习", "神经网络的梯度下降"),
    ("AI与机器学习", "词向量 Word2Vec"),
    ("AI与机器学习", "强化学习基础概念"),
    ("AI与机器学习", "AI Agent 智能体"),
    ("AI与机器学习", "多模态大模型"),
    ("AI与机器学习", "扩散模型生成图片"),
    ("AI与机器学习", "大模型微调 LoRA"),
    # 编程与开发（15）
    ("编程与开发", "Python 装饰器"),
    ("编程与开发", "Python 列表推导式"),
    ("编程与开发", "JavaScript 闭包"),
    ("编程与开发", "TypeScript 类型系统"),
    ("编程与开发", "React Hooks 的使用"),
    ("编程与开发", "Vue 响应式原理"),
    ("编程与开发", "Git 分支管理"),
    ("编程与开发", "RESTful API 设计"),
    ("编程与开发", "二叉搜索树"),
    ("编程与开发", "快速排序算法"),
    ("编程与开发", "时间复杂度分析"),
    ("编程与开发", "面向对象编程三大特性"),
    ("编程与开发", "单元测试与 TDD"),
    ("编程与开发", "代码重构技巧"),
    ("编程与开发", "正则表达式入门"),
    # 计算机与网络（10）
    ("计算机与网络", "HTTP 协议基础"),
    ("计算机与网络", "TCP 三次握手"),
    ("计算机与网络", "DNS 域名解析"),
    ("计算机与网络", "操作系统进程与线程"),
    ("计算机与网络", "内存管理与垃圾回收"),
    ("计算机与网络", "数据库索引原理"),
    ("计算机与网络", "SQL 多表连接查询"),
    ("计算机与网络", "Redis 缓存应用"),
    ("计算机与网络", "Docker 容器化"),
    ("计算机与网络", "微服务架构"),
    # 自然科学（12）
    ("自然科学", "黑洞的形成"),
    ("自然科学", "量子力学不确定性原理"),
    ("自然科学", "光合作用过程"),
    ("自然科学", "DNA 双螺旋结构"),
    ("自然科学", "相对论时空弯曲"),
    ("自然科学", "元素周期表规律"),
    ("自然科学", "化学反应平衡"),
    ("自然科学", "地震成因与板块构造"),
    ("自然科学", "全球气候变暖"),
    ("自然科学", "人类免疫系统"),
    ("自然科学", "病毒与疫苗原理"),
    ("自然科学", "光的折射与反射"),
    # 历史与人文（12）
    ("历史与人文", "秦始皇统一六国"),
    ("历史与人文", "丝绸之路的历史作用"),
    ("历史与人文", "文艺复兴运动"),
    ("历史与人文", "工业革命的影响"),
    ("历史与人文", "五四运动"),
    ("历史与人文", "二战的转折点"),
    ("历史与人文", "唐朝的兴衰"),
    ("历史与人文", "古埃及金字塔"),
    ("历史与人文", "罗马帝国的兴亡"),
    ("历史与人文", "印刷术的发明与传播"),
    ("历史与人文", "美国独立战争"),
    ("历史与人文", "冷战格局的形成"),
    # 经济与商业（10）
    ("经济与商业", "供需关系与价格"),
    ("经济与商业", "复利效应"),
    ("经济与商业", "通货膨胀"),
    ("经济与商业", "GDP 的含义"),
    ("经济与商业", "股票的估值方法"),
    ("经济与商业", "边际效用递减"),
    ("经济与商业", "机会成本"),
    ("经济与商业", "商业模式画布"),
    ("经济与商业", "供应链管理"),
    ("经济与商业", "市场营销 4P 理论"),
    # 生活与健康（10）
    ("生活与健康", "咖啡的烘焙方式"),
    ("生活与健康", "科学健身增肌"),
    ("生活与健康", "睡眠周期与睡眠质量"),
    ("生活与健康", "营养均衡膳食"),
    ("生活与健康", "心肺复苏急救"),
    ("生活与健康", "家庭理财规划"),
    ("生活与健康", "摄影构图技巧"),
    ("生活与健康", "手机摄影的光线运用"),
    ("生活与健康", "家常菜烹饪技巧"),
    ("生活与健康", "收纳整理方法"),
    # 语言与学习（8）
    ("语言与学习", "英语时态体系"),
    ("语言与学习", "英语词根记忆法"),
    ("语言与学习", "汉语拼音声调"),
    ("语言与学习", "日语五十音图"),
    ("语言与学习", "艾宾浩斯遗忘曲线"),
    ("语言与学习", "费曼学习法"),
    ("语言与学习", "思维导图"),
    ("语言与学习", "外语口语练习方法"),
    # 文化与艺术（6）
    ("文化与艺术", "中国传统节日"),
    ("文化与艺术", "京剧艺术"),
    ("文化与艺术", "中国书法"),
    ("文化与艺术", "围棋规则与策略"),
    ("文化与艺术", "电影蒙太奇手法"),
    ("文化与艺术", "交响乐赏析"),
    # 前沿技术（5）
    ("前沿技术", "区块链原理"),
    ("前沿技术", "智能家居"),
    ("前沿技术", "电动汽车电池"),
    ("前沿技术", "无人机技术"),
    ("前沿技术", "3D 打印"),
]

# 5 种自然语言输入句式（模拟真实用户的不同输入风格）
TEMPLATES: list[tuple[str, str]] = [
    ("t1", "{t}"),
    ("t2", "{t}是什么？"),
    ("t3", "帮我讲解一下 {t}，然后出题考考我"),
    ("t4", "我想学习 {t}"),
    ("t5", "帮我出一套关于 {t} 的练习题"),
]


def build_cases() -> list[dict]:
    """构建 500 条用例并分配模式（每主题 3 条 model + 2 条 search，跨主题轮换）。

    分配规则：主题索引 i、模板索引 t；t ∈ {i%5, (i+1)%5} → search，其余 → model。
    该规则保证每个主题两个模式都有覆盖、每种模板在两个模式中的样本量均衡
    （每种模板：search 40 条 + model 60 条）。

    执行顺序保留「先所有主题的模板 1，再模板 2……」的结构：同一主题的
    变体间隔 ≥ 60 条执行，避免检索缓存导致数据失真。
    """
    cases: list[dict] = []
    for template_index, (template_id, template) in enumerate(TEMPLATES):
        for topic_index, (category, topic) in enumerate(TOPICS):
            is_search = template_index in {topic_index % 5, (topic_index + 1) % 5}
            cases.append(
                {
                    "category": category,
                    "topic": topic,
                    "template": template_id,
                    "mode": "search" if is_search else "model",
                    "input": template.format(t=topic),
                }
            )
    for index, case in enumerate(cases, start=1):
        case["case_id"] = f"c{index:04d}"
    return cases


# ---- 结果读写 ----


def load_records(path: Path) -> list[dict]:
    """读取既有 JSONL 结果（跳过坏行）。"""
    if not path.exists():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def append_record(handle, record: dict) -> None:
    """增量写入一条记录并立即落盘（保证中断不丢数据）。"""
    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


# ---- 任务提交与轮询 ----


def _db_session():
    from app.services import task_service

    return task_service.get_session_factory()()


def submit_case(case: dict) -> str:
    """创建并提交一条生成任务（与小程序端相同链路），返回 task_id。"""
    from app.models.quiz import QuizGenerateRequest
    from app.services import task_service

    request = QuizGenerateRequest(
        user_input=case["input"],
        question_count=QUESTION_COUNT,
        difficulty=DIFFICULTY,
        question_types=QUESTION_TYPES,
    )
    session = task_service.get_session_factory()()
    try:
        task = task_service.create_task(session, request, user_id=None)
    finally:
        session.close()
    task_service.submit_task(task.task_id)
    return task.task_id


def poll_tasks(task_ids: list[str]) -> dict:
    """批量查询任务当前状态：task_id -> GenerationTask。"""
    from sqlalchemy import select

    from app.models.task import GenerationTask

    if not task_ids:
        return {}
    session = _db_session()
    try:
        rows = session.scalars(
            select(GenerationTask).where(GenerationTask.task_id.in_(task_ids))
        ).all()
        return {row.task_id: row for row in rows}
    finally:
        session.close()


def build_record(case: dict, row, wall_sec: float, status_override: str | None = None) -> dict:
    """把任务终态整理为一条结果记录，用于统计。"""
    created, finished = row.created_at, row.finished_at
    latency = (finished - created).total_seconds() if (created and finished) else None
    record: dict = {
        "case_id": case["case_id"],
        "category": case["category"],
        "topic": case["topic"],
        "template": case["template"],
        "mode": case["mode"],
        "input": case["input"],
        "task_id": row.task_id,
        "status": status_override or row.status,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "created_at": created.isoformat() if created else None,
        "finished_at": finished.isoformat() if finished else None,
        "latency_sec": round(latency, 3) if latency is not None else None,
        "wall_sec": round(wall_sec, 3),
        "search_count": None,
        "sources_n": None,
        "questions_n": None,
    }
    if row.result:
        trace = row.result.get("agent_trace") or {}
        record["search_count"] = trace.get("search_count")
        record["sources_n"] = len(row.result.get("sources") or [])
        record["questions_n"] = len(row.result.get("questions") or [])
    return record


# ---- 统计报告 ----


def percentile(sorted_values: list[float], p: float) -> float | None:
    """线性插值百分位（p 为 0~1）。"""
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * p
    low, high = math.floor(k), math.ceil(k)
    if low == high:
        return sorted_values[low]
    return sorted_values[low] * (high - k) + sorted_values[high] * (k - low)


def _fmt(value: float | None, unit: str = "", digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value:.{digits}f}{unit}"


def print_report(records: list[dict], title: str = "出题批量基准测试报告") -> None:
    """输出统计报告：总成功率 + 耗时分布 + 分组统计 + 失败明细。"""
    total = len(records)
    ok = [r for r in records if r["status"] == "done"]
    failed = [r for r in records if r["status"] == "failed"]
    timed_out = [r for r in records if r["status"] == "timeout"]
    success_rate = len(ok) / total * 100 if total else 0.0

    print()
    print("=" * 64)
    print(title)
    print("=" * 64)
    print(f"用例总数：{total}    成功：{len(ok)}    失败：{len(failed)}    超时未判定：{len(timed_out)}")
    print(f"成功率：{success_rate:.2f}%（成功 / 总数）")

    latencies = sorted(r["latency_sec"] for r in ok if r["latency_sec"] is not None)
    if latencies:
        mean = sum(latencies) / len(latencies)
        print()
        print("【耗时统计 · 成功任务（服务器口径 finished_at - created_at）】")
        print(
            f"  平均：{mean:.1f}s    中位数：{percentile(latencies, 0.5):.1f}s    "
            f"P90：{percentile(latencies, 0.90):.1f}s    P95：{percentile(latencies, 0.95):.1f}s    "
            f"P99：{percentile(latencies, 0.99):.1f}s"
        )
        print(f"  最短：{latencies[0]:.1f}s    最长：{latencies[-1]:.1f}s")

    fail_lat = sorted(r["latency_sec"] for r in failed if r["latency_sec"] is not None)
    if fail_lat:
        print(
            f"【耗时 · 失败任务】n={len(fail_lat)}    "
            f"平均：{sum(fail_lat) / len(fail_lat):.1f}s    最短：{fail_lat[0]:.1f}s    最长：{fail_lat[-1]:.1f}s"
        )

    searches = [r["search_count"] for r in ok if r.get("search_count") is not None]
    if searches:
        with_sources = sum(1 for r in ok if (r.get("sources_n") or 0) > 0)
        print(
            f"【知识溯源】平均检索 {sum(searches) / len(searches):.2f} 次/题    "
            f"含联网来源的占 {with_sources / len(ok) * 100:.1f}%（{with_sources}/{len(ok)}）"
        )

    def group_stats(key: str) -> None:
        groups: dict[str, list[dict]] = {}
        for r in records:
            groups.setdefault(r[key], []).append(r)
        print()
        print(f"【按{key}】")
        for name, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            group_ok = [r for r in items if r["status"] == "done"]
            group_lat = [r["latency_sec"] for r in group_ok if r["latency_sec"] is not None]
            avg = f"{sum(group_lat) / len(group_lat):.1f}s" if group_lat else "-"
            print(
                f"  {name:<10} {len(items):>3} 条   成功率 {len(group_ok) / len(items) * 100:6.1f}%   平均耗时 {avg}"
            )

    group_stats("mode")
    group_stats("category")
    group_stats("template")

    if failed or timed_out:
        print()
        print("【失败明细】（最多显示 20 条）")
        for record in (failed + timed_out)[:20]:
            message = str(record.get("error_message") or "")[:60]
            print(
                f"  {record['case_id']}  [{record['status']}] code={record.get('error_code')}  "
                f"{message}  输入：{record['input'][:40]}"
            )
    print()


# ---- 主流程 ----


def run(args: argparse.Namespace) -> int:
    # 覆盖本脚本进程的线程池并发（不影响 .env / 其他服务）；必须在导入 app 模块前设置
    os.environ["TASK_WORKER_CONCURRENCY"] = str(args.concurrency)

    from app.core.config import get_settings

    settings = get_settings()
    assert settings.task_worker_concurrency == args.concurrency, "并发覆盖失败"

    if args.mode == "search" and not settings.tavily_api_key:
        print("[WARN] .env 未配置 TAVILY_API_KEY：search 模式将退化为纯模型出题")
    if args.mode == "model":
        # 纯模型模式：进程内清空联网凭据（等价「未配置任何渠道」的兼容模式），
        # 仅作用于本脚本进程；不影响 .env 与其他服务。
        settings.tavily_api_key = ""
        assert settings.tavily_api_key == "", "联网禁用失败"

    cases = build_cases()
    cases = [case for case in cases if case["mode"] == args.mode]
    if args.total > 0:
        cases = cases[: args.total]
    if not cases:
        print(f"[FAIL] mode={args.mode} 没有可执行用例")
        return 1

    result_path = Path(args.result) if args.result else RESULTS_DIR / f"bench_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    result_path.parent.mkdir(parents=True, exist_ok=True)

    existing = load_records(result_path)
    done_ids = {r["case_id"] for r in existing}
    pending = deque(case for case in cases if case["case_id"] not in done_ids)

    print(f"[配置] 模式：{args.mode}（{'联网检索 + 出题' if args.mode == 'search' else '纯模型出题'}）")
    print(f"[配置] 用例 {len(cases)} 条（已完成 {len(existing)}，待执行 {len(pending)}）")
    print(f"[配置] 并发 {args.concurrency}（进程内覆盖 task_worker_concurrency）")
    print(f"[配置] 参数：{QUESTION_COUNT} 题 / {DIFFICULTY} / {'+'.join(QUESTION_TYPES)}")
    print(f"[配置] 结果文件：{result_path}")
    print(f"[配置] 轮询间隔 {args.poll_interval}s；单条超时 {args.timeout}s")
    print("-" * 64)

    inflight: dict[str, dict] = {}  # task_id -> {case, t_submit}
    completed = 0
    run_started = time.monotonic()

    with result_path.open("a", encoding="utf-8") as handle:
        try:
            while pending or inflight:
                # 1) 补满并发窗口
                while len(inflight) < args.concurrency and pending:
                    case = pending.popleft()
                    try:
                        task_id = submit_case(case)
                    except Exception as exc:  # noqa: BLE001 - 提交失败也记录为失败样本
                        record = {
                            "case_id": case["case_id"],
                            "category": case["category"],
                            "topic": case["topic"],
                            "template": case["template"],
                            "mode": case["mode"],
                            "input": case["input"],
                            "task_id": None,
                            "status": "failed",
                            "error_code": -1,
                            "error_message": f"提交失败：{type(exc).__name__}: {exc}"[:300],
                            "created_at": None,
                            "finished_at": None,
                            "latency_sec": None,
                            "wall_sec": 0.0,
                        }
                        append_record(handle, record)
                        completed += 1
                        print(f"  [{completed:>3}/{len(cases)}] {case['case_id']} 提交失败：{exc}")
                        continue
                    inflight[task_id] = {"case": case, "t_submit": time.monotonic()}
                    print(f"  [{len(inflight)} 并发中] 提交 {case['case_id']}  {case['input'][:48]}")

                # 2) 轮询在途任务
                time.sleep(args.poll_interval)
                now = time.monotonic()
                rows = poll_tasks(list(inflight))
                for task_id in list(inflight):
                    row = rows.get(task_id)
                    info = inflight[task_id]
                    case = info["case"]
                    wall_sec = now - info["t_submit"]

                    if row is not None and row.status in ("done", "failed"):
                        record = build_record(case, row, wall_sec)
                        append_record(handle, record)
                        completed += 1
                        del inflight[task_id]
                        mark = "OK " if record["status"] == "done" else "FAIL"
                        latency = f"{record['latency_sec']:.1f}s" if record["latency_sec"] is not None else "-"
                        print(
                            f"  [{completed:>3}/{len(cases)}] {case['case_id']} {mark} "
                            f"{latency}  {case['input'][:40]}"
                        )
                    elif wall_sec > args.timeout:
                        # 超时未判定：记录当前状态后不再等待（任务可能仍在后台运行）
                        record = build_record(case, row, wall_sec, status_override="timeout") if row else {
                            "case_id": case["case_id"],
                            "category": case["category"],
                            "topic": case["topic"],
                            "template": case["template"],
                            "mode": case["mode"],
                            "input": case["input"],
                            "task_id": task_id,
                            "status": "timeout",
                            "error_code": None,
                            "error_message": f"超过 {args.timeout}s 未到终态",
                            "created_at": None,
                            "finished_at": None,
                            "latency_sec": None,
                            "wall_sec": round(wall_sec, 3),
                        }
                        append_record(handle, record)
                        completed += 1
                        del inflight[task_id]
                        print(f"  [{completed:>3}/{len(cases)}] {case['case_id']} TIMEOUT > {args.timeout}s")
        except KeyboardInterrupt:
            print("\n[中断] 收到 Ctrl+C：已完成的记录均已写入结果文件，可用同一文件续跑。")
        finally:
            if inflight:
                print(f"[注意] 仍有 {len(inflight)} 条任务在途未记录（可用同一结果文件续跑）")

    elapsed = time.monotonic() - run_started
    records = load_records(result_path)
    print(f"\n[完成] 本次运行 {completed} 条，用时 {elapsed / 60:.1f} 分钟；累计记录 {len(records)} 条")
    print_report(records, title=f"出题批量基准测试报告（{result_path.name}）")
    return 0


def stats_only(args: argparse.Namespace) -> int:
    if not args.result:
        print("[FAIL] --stats-only 需要同时指定 --result 结果文件（逗号分隔可传多个，合并统计）")
        return 1
    paths = [Path(p.strip()) for p in args.result.split(",") if p.strip()]
    records: list[dict] = []
    for path in paths:
        part = load_records(path)
        if not part:
            print(f"[WARN] 结果文件无记录：{path}")
            continue
        print(f"[读取] {path}（{len(part)} 条记录）")
        records.extend(part)
    if not records:
        print("[FAIL] 所有结果文件均无记录")
        return 1
    title = "出题批量基准测试报告" + (f"（合并 {len(paths)} 个结果文件）" if len(paths) > 1 else f"（{paths[0].name}）")
    print_report(records, title=title)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="出题批量基准测试（成功率 + 耗时）")
    parser.add_argument("--mode", choices=["model", "search"], default="search",
                        help="model=纯模型出题（300 条子集）/ search=联网检索 + 出题（200 条子集）")
    parser.add_argument("--total", type=int, default=0, help="在该模式子集内截取的条数（默认 0=全部）")
    parser.add_argument("--concurrency", type=int, default=5, help="并发数（默认 5，仅脚本进程生效）")
    parser.add_argument("--poll-interval", type=float, default=0.5, help="轮询间隔秒（默认 0.5）")
    parser.add_argument("--timeout", type=float, default=600.0, help="单条超时秒（默认 600）")
    parser.add_argument("--result", default="", help="结果文件路径（默认自动生成；传入已有文件可续跑；stats-only 时逗号分隔可合并多个）")
    parser.add_argument("--stats-only", action="store_true", help="只统计既有结果，不执行新任务")
    args = parser.parse_args()

    try:
        if args.stats_only:
            return stats_only(args)
        return run(args)
    except Exception as exc:  # noqa: BLE001 - 顶层兜底，保证脚本可读报错
        print(f"[FAIL] 执行异常：{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
