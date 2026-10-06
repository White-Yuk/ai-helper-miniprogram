# Tasks

## 1. 依赖与配置

- [x] 1.1 `backend/requirements.txt` 新增 `langchain-tavily`；执行 `pip install -r requirements.txt`，验证 `python -c "from langchain_tavily import TavilySearch, TavilyExtract"` 成功（langgraph 已随 langchain 1.x 在环境内，确认即可）
- [x] 1.2 `app/core/config.py` 调整配置项：新增 `tavily_api_key=""`、`search_agent_timeout_seconds=45`、`search_agent_max_tool_calls=4`、`search_max_results=10`、`search_summary_max_chars=5000`、`assessment_timeout_seconds=20`、`task_ttl_hours=24`、`task_worker_concurrency=2`、`search_country=""`、`search_auto_parameters=True`；移除旧检索项（`search_timeout_seconds` / `search_score_threshold` / `search_snippet_max_chars`）；新增默认值断言测试并运行 pytest 通过
- [x] 1.3 `backend/README.md` 与 `backend/.env.example` 更新：Tavily Key 获取与配置、清空即回滚、任务化生成说明（含 60s 超时背景与同步接口保留用途）；按文档步骤核对描述与代码一致

## 2. 知识获取 Agent

- [x] 2.1 新增知识获取 Agent 模块 `app/services/knowledge_agent.py`：3 个工具构建——`tavily_search_basic`（10 条摘要、**锁定 `search_depth="basic"`、关闭 auto_parameters**，轻快 1 credit）/ `tavily_search_deep`（5 条完整内容、**auto_parameters 取配置项**，允许自动升级）/ `tavily_extract`（不预设深度）；`create_agent` 组装（LangChain 1.x API，`system_prompt=` 参数）、45s 线程池超时护栏、输出截断、来源提取（从工具消息解析标题 / URL 并去重）；构建结果进程级缓存复用；**实现注记："实例值优先于运行时值"——除档位有意锁定项（basic 档 search_depth）外，实例化时不得设置可动态参数（time_range / topic / include_domains 等保持 None）**
- [x] 2.2 新增 Agent Prompt `app/prompts/agent_prompt.py`：多角度搜索 + 以多数为准（点名术语歧义场景）、**档位与动态参数策略（常见主题走 basic 档；复杂/歧义主题进 deep 档；时效主题设 time_range；限定来源用 include_domains；"最新/近期"结合 start_date/end_date）**、URL 识别（**提取失败时尝试转关键词搜索补救**）、≤4 次工具调用、只基于工具结果、未找到须明确说明、输出结构化摘录（领域判断 + 要点 + 来源）
- [x] 2.3 编写 Agent 边界测试 `tests/test_search_service.py`（patch `_build_agent` + mock 调用 + 注入 Fake 步骤写入器）：开关关闭 / 未配置 Key 返回空、超时降级、异常降级、输出截断、来源提取、步骤回调写入；运行 pytest 通过
- [x] 2.4 Agent Prompt 契约测试（关键要素断言：3 个工具名、调用次数上限、"以多数为准" / 领域判定、动态参数指引、URL 与提取失败补救、"未找到"说明）；运行 pytest 通过

## 3. 异步任务基础设施

- [x] 3.1 `app/models/task.py` 新增 `GenerationTask` 模型（id / user_id / status / steps JSON / request JSON / result JSON / error_code / error_message / created_at / updated_at / finished_at）并注册到模型体系；更新建表入口（`init_db` 覆盖新表）；编写 schema 单测并 pytest 通过
- [x] 3.2 新增 `app/services/task_service.py`：`create_task`（含懒清理过期任务）、`submit_task`（应用级线程池，并发数取配置）、`_run_task`（状态机 pending→running→done/failed；步骤写入；成功后登录用户题库入库；业务异常错误码原样保留（如 4006），未知异常兜底 4001；使用独立数据库会话）、`get_task`（归属校验）、步骤写入器 `make_step_writer`；服务启动时将残留 running 任务标记为 failed
- [x] 3.3 任务服务单测 `tests/test_task_service.py`：创建 / 状态机流转（成功、业务失败 4006、未知异常 4001）/ 步骤写入 / 归属校验 / 过期清理 / 残留任务处理（patch 执行函数，离线可跑）；pytest 通过

## 4. 出题 Prompt v2

- [x] 4.1 `app/prompts/quiz_prompt.py` 升级 v2：新增 `reference_context` 模板变量、资料使用规则（依据资料 / 以资料为准 / 防注入 / 不编造）、无资料占位提示；文件头注明版本与变更记录
- [x] 4.2 更新 `tests/test_prompt_contract.py`：渲染传入 `reference_context`，新增断言（参考资料区、资料规则、无资料提示语）；pytest 通过

## 5. 可靠性评估器

- [x] 5.1 在 `app/models/quiz.py` 增加 `ReliabilityAssessment`；新增 `app/llm/assessor.py`（评估 Prompt + 结构化输出链 + 1 次重试 + 20s 超时）与 `tests/test_assessor.py`（mock LLM：可靠 / 不可靠 / 重试 / 最终失败）；pytest 通过

## 6. 服务层编排

- [x] 6.1 编写编排场景测试（扩展 `tests/test_quiz_service.py`，注入 Fake Agent 结果 / Fake Assessor / Fake 步骤写入器）：行为矩阵全场景（未配置 = 现状、有有效内容、无有效内容可靠、无有效内容不可靠 → 4006、Agent 超时降级、URL 成功、URL 提取失败补救无果后走无资料分支、`sources` / `agent_trace` 组装、步骤回调触发）；运行确认新用例先失败（红）
- [x] 6.2 `app/models/quiz.py` 增加 `QuizSource`、`AgentTrace` 模型与 `QuizGenerateData.sources` / `agent_trace` 可选字段；更新 `tests/test_schemas.py`；pytest 通过
- [x] 6.3 实现 `quiz_service` 编排（Agent 调用 → 有效内容判定 → 守卫 → 出题重试 → 组装 `sources` / `agent_trace`；新增可选 `on_step` 回调参数用于阶段步骤上报）；6.1 全部转绿

## 7. 接口层

- [x] 7.1 `api/v1/routes/quiz.py`：新增 `POST /quiz/tasks`（可选登录、创建任务并提交执行、立即返回 `task_id`）与 `GET /quiz/tasks/{task_id}`（返回状态 / 步骤 / 结果 / 错误；不存在或过期 4005）；原 `POST /quiz/generate` 同步接口保留不变
- [x] 7.2 扩展 `tests/test_quiz_api.py`（或新增任务接口测试文件）：创建任务返回 `task_id`（patch 提交函数防止测试中真实执行）、查询各状态（pending / running / done / failed 含 4006）、4005 场景、同步接口现有行为不变；pytest 全绿（含现有用例）

## 8. 前端（generating 页任务流程）

- [x] 8.1 `services/api.ts`：新增 `createQuizTask`（POST /quiz/tasks）与 `getQuizTask`（GET /quiz/tasks/{id}）、轮询封装 `waitQuizTask`（默认 2s 间隔 / 150 次上限；任务失败转为 `ApiError` 复用现有错误处理）；修正超时注释（说明小程序端 60s 上限；同步接口保留供 H5 调试）；`types` 增加任务相关类型
- [x] 8.2 `pages/generating/index.tsx`：流程改为"创建任务 → 轮询（步骤实时渲染）→ 完成展示知识溯源卡片进入闯关 / 失败按错误码展示（4006 专用引导）/ 轮询超上限提示超时"；页面卸载时停止轮询
- [ ] 8.3 人工验证（H5 / 微信开发者工具）：创建任务后立刻进入轮询界面、步骤逐条更新、完成后溯源卡片展示、4006 与普通失败展示正确、页面退出轮询停止

## 9. 集成验收

- [x] 9.1 后端全量回归：`cd backend && pytest` 全部通过（现有 150+ 测试 + 新增）
- [x] 9.2 真实联调（配置 `TAVILY_API_KEY`）：用 "Harness Engineering" 验证领域判定（题目内容为 AI 工程含义）与来源 / 轨迹字段；输入一个真实网页 URL 验证提取出题（含提取失败补救路径的观察）；清空 Key 验证降级兼容；服务重启后查询已完成任务验证持久化
- [ ] 9.3 端到端走查（小程序端）：从输入到闯关全流程走任务轮询体验（校验 60s 上限下无超时问题）；断网 / 超时场景降级表现；记录实际生成耗时（作为 Agent 超时参数调优依据）
