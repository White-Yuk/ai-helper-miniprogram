# 出题功能批量测试报告（500 条）

- 测试日期：2026-10-07
- 测试脚本：`backend/scripts/bench_quiz_generation.py`（可复现）
- 原始数据（每条含 case/task_id/状态/耗时/检索次数）：
  - `backend/scripts/results/bench_model_300.jsonl`（300 条 · 纯模型）
  - `backend/scripts/results/bench_search_200.jsonl`（200 条 · 联网增强）

## 测试条件

- **链路**：与小程序端完全一致的异步任务流水线（`create_task` → 线程池执行 → 轮询终态），真实调用 DeepSeek；联网模式另真实调用 Tavily
- **参数统一**：5 题 / mixed 难度 / 单选 + 多选 + 判断（产品默认）
- **用例设计**：100 个主题（覆盖 10 个知识领域）× 5 种自然语言输入句式（短语 / 提问 / 讲解请求 / 学习意图 / 出题请求）；每个主题 3 条纯模型 + 2 条联网增强
- **执行方式**：5 并发（脚本进程内，未改服务配置），两批串行执行
- **耗时口径**：服务端 `finished_at - created_at`（不含客户端轮询间隔）

## 总体结果

| 指标 | 数值 |
| --- | --- |
| 总用例 | **500** |
| 成功 | **500** |
| 失败 | 0 |
| **成功率** | **100%** |
| 平均耗时 | **10.0s** |
| 中位数 | 6.0s |
| P90 / P95 / P99 | 20.0s / 22.0s / 28.0s |
| 最短 / 最长 | 3.0s / 42.0s |

## 分模式结果

| 模式 | 条数 | 成功率 | 平均 | 中位 | P90 | P95 | P99 | 最长 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 纯模型出题 | 300 | 100% | **5.3s** | 5.0s | 6.0s | 6.3s | 13.0s | 19.0s |
| 联网检索 + 出题 | 200 | 100% | **17.1s** | 16.0s | 23.0s | 26.0s | 35.0s | 42.0s |

## 联网模式检索明细

- 检索调用：**518 次**（轻快档 484 + 深度档 34），平均 **2.59 次/题**
- 知识来源覆盖：**100%**（200/200 题库均携带真实网页来源）
- Tavily 消耗估算：~518–552 credits（约为免费月额度 1000 的一半）

## 分领域结果（全部 100% 成功）

| 领域 | 条数 | 平均耗时 |
| --- | --- | --- |
| 编程与开发 | 75 | 9.7s |
| AI 与机器学习 | 60 | 10.2s |
| 自然科学 | 60 | 10.2s |
| 历史与人文 | 60 | 10.2s |
| 计算机与网络 | 50 | 9.9s |
| 经济与商业 | 50 | 9.9s |
| 生活与健康 | 50 | 9.8s |
| 语言与学习 | 40 | 10.7s |
| 文化与艺术 | 30 | 9.5s |
| 前沿技术 | 25 | 10.3s |

## 观察与说明

1. **长尾可控**：联网模式仅 5 条超过 30s（均为触发 3 次检索的复杂题，最长 42s），远低于小程序 60s 超时线；纯模型 15 条超过 10s（少数走重试路径），最长 19s
2. **检索档位以轻快为主**：Agent 自主选择策略下，94% 的检索为轻快档（1 credit），符合"轻快优先"的设计目标
3. **无知识盲区误判**：200 条联网任务无一触发 4006 守卫（均为正常主题，评估器未误杀）
4. **Tavily 统计延迟**：其 usage API 有 30–60 分钟入账延迟（试跑 57 次调用事后入账 59 credits，精确吻合计费规则）

## 复现方式

```bash
cd backend
# 纯模型批次（300 条）
.venv/Scripts/python.exe scripts/bench_quiz_generation.py --mode model  --result scripts/results/bench_model_300.jsonl
# 联网批次（200 条）
.venv/Scripts/python.exe scripts/bench_quiz_generation.py --mode search --result scripts/results/bench_search_200.jsonl
# 合并统计
.venv/Scripts/python.exe scripts/bench_quiz_generation.py --stats-only --result "scripts/results/bench_model_300.jsonl,scripts/results/bench_search_200.jsonl"
```
