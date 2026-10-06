# Design

## Context

动机与范围见 proposal.md；行为契约见 specs/。

现状与约束（支撑本设计的关键事实）：

- **出题链路**：`POST /quiz/tasks`（异步任务）→ 线程池执行【`knowledge_agent.acquire_knowledge`（Tavily Agent：basic / deep / extract 3 工具，45s 超时，进程级缓存，`RunnableConfig` 无关的纯函数式工具）→ 有效内容判定 → （无资料时）`assessor` 知识守卫 → 出题链】→ 任务写入 steps / result → 客户端轮询。同步接口 `POST /quiz/generate` 共用同一编排函数。
- **任务执行上下文**：`task_service._run_task` 已携带 `user_id`（可空），但目前不向下传递给 Agent（Agent 无需用户上下文）。
- **测试约定**：全部离线（FakeChain 注入、不触真实 LLM / 网络）；统一响应 `{code,message,data}`；错误码体系 4000-4006。
- **环境事实（2026-10-07 实测）**：Python 3.14.4；`pip install --dry-run langchain-community langchain-text-splitters langchain-chroma chromadb pypdf docx2txt` 全树可解析（langchain-community 0.4.2 / langchain-text-splitters 1.1.3 / langchain-chroma 1.1.0 / chromadb 1.5.9，均有 Windows wheel，无需编译器）；`langchain 1.4.3` 下 `BaseTool` 的 `RunnableConfig` 注入已验证（工具可读 `config["configurable"]["user_id"]`，且 `config` 参数不暴露给 LLM）。
- **技术选型对齐（2026-10-07，依据 doc/RAG技术选型.md，已查证）**：RAG 链路采用 LangChain 组件——文档加载 PyPDFLoader / Docx2txtLoader（langchain-community）、文本分块 langchain-text-splitters、向量存储 langchain-chroma、Embedding 用 langchain-openai 的 `OpenAIEmbeddings` 对接百炼。已知边界：langchain-community 被官方标记 deprecated（loaders 仍为官方文档推荐路径，2026 年仍在发版）；`unstructured`（UnstructuredMarkdownLoader 底层）依赖重（nltk / numba / llvmlite）且 Windows 需额外 `python-magic-bin` 否则报 libmagic 错误 → Markdown 主方案改用 `TextLoader`（见 D3）。
- **百炼 text-embedding-v4（2026-10-07 查证）**：维度可选 2048/1536/1024（默认）/768/512/256/128/64；单请求最多 10 条；单条 ≤8192 token；单批 ≤33000 token；0.0005 元/千 token（免费额度 100 万 token）；OpenAI 兼容接口，旧域名 `https://dashscope.aliyuncs.com/compatible-mode/v1` 官方标注「仍可正常使用」（新域名需业务空间 ID，配置项可自填）。
- **小程序硬约束**：`wx.request` / `wx.uploadFile` 最长 60s 超时 → 长耗时处理必须异步任务 + 轮询（沿用现有模式）。

## Goals / Non-Goals

**Goals:**

- 用户文档「上传即受理」：后台异步完成解析 → 分块 → 向量化 → 入库，进度与失败原因全程可见。
- 出题 Agent 自主路由：有就绪文档的用户，出题时 Agent 可获得「资料库检索」工具；资料库命中优先进出题依据，不足时联网补充。
- 严格用户隔离：文档、向量、检索全程按 `user_id` 过滤，向量库与查询不可能跨用户串数据。
- 全链路可降级：未配置百炼 / 无文档 / 资料库异常 → 出题行为与现状一致或继续可用渠道，任务永不因资料库失败。
- 与现有架构模式对齐：线程池 + 独立会话、steps 进度、进程级 Agent 缓存、测试离线。

**Non-Goals:**

- 不做独立问答 / 生成回答（人工确认推迟）。
- 不做多知识库 / 文件夹（单库）；不做文档在线预览 / 分享。
- 不做 OCR（扫描版 PDF 解析失败即失败）；不支持 .doc / .txt 等其余格式。
- 不做文档处理失败的一键重试（第一版用「删除后重新上传」替代；列为 Open Question）。
- 不做向量库外部服务部署（本地 PersistentClient 嵌入进程，非 Chroma Server）。
- 不做 chunk 级页码 / 章节元数据（后续可扩展）。

## Decisions

### D1. 总体架构：文档处理流水线与出题链路扩展相互独立

- **文档链路**（新）：`POST /documents`（multipart 上传 → 校验 → 存原文件 + 建文档记录 pending）→ 独立线程池执行【解析 → 分块 → 向量化（分批）→ 写入 Chroma】→ 更新文档状态（ready / failed）；客户端轮询 `GET /documents` 列表获取状态与步骤。
- **出题链路**（改造）：`acquire_knowledge(user_input, user_id, on_step)` → Agent 工具集 = Tavily×3 +【该用户有就绪文档时】资料库检索工具 → 有效内容判定（含资料库命中）→ 注入出题 Prompt；来源合并（联网 + 资料库）。
- 替代方案：文档处理复用 `generation_tasks` 任务表（否决：状态域不同，documents 表自带状态即任务状态，避免双表同步）；同步上传处理（否决：大文档分钟级，违反 60s 约束）。

### D2. 数据模型：documents 表 + Chroma 每用户 collection

- **documents 表**（`app/models/document.py`，表 `documents`）：

| 字段 | 说明 |
| --- | --- |
| id | 自增主键 |
| doc_id | 文档号 `doc_xxx`（随机生成，对外标识与归属校验用） |
| user_id | 归属用户（索引；必填——上传需登录） |
| filename | 原始文件名（仅展示用，存储不信任该值） |
| file_type | pdf / docx / md |
| file_size | 字节数 |
| status | pending / processing / ready / failed |
| steps | 步骤列表 JSON（同生成任务格式：key/label/detail/state/ts） |
| error_message | 失败原因（可读） |
| chunk_count / char_count | 处理结果统计 |
| created_at / updated_at / finished_at | 时间戳 |

- **Chroma（经 langchain-chroma）**：`Chroma(persist_directory=backend/data/chroma, collection_metadata={"hnsw:space": "cosine"})` 本地持久化；**每个用户一个 collection（`kb_{user_id}`）**——用户隔离由 collection 物理承载（对齐用户技术选型：隔离清晰、整库删除简单、避免过滤遗漏）；collection 内 metadata 区分文档与块：`{doc_id, filename, chunk_index}`；**只写入处理成功（ready）文档的向量**（未就绪文档天然无向量）。collection 惰性创建（用户首次上传时）。
- **用户隔离选型**：每用户一个 collection（替代「单 collection + where 过滤」：单库产品下 collection 数量可控；删除用户全部数据 = 删除整个 collection，语义干净）。
- **存储**：原文件 `backend/data/uploads/{user_id}/{doc_id}.{ext}`（不经静态目录暴露，隐私）；`backend/data/` 整体加入 `.gitignore`。
- **删除语义**：删除 = 记录删除 + 用户 collection 内按 `where={"doc_id":...}` 删除向量 + 原文件删除；处理中删除 = 记录标记删除后，后台任务在每次写库 / 写向量前复查记录是否仍存在，不存在则丢弃结果（防竞态残留）。

### D3. 处理流水线：LangChain loaders + splitters + 分批向量化

- **解析（LangChain loaders，统一产出 `Document` 列表）**：
  - PDF：`PyPDFLoader`（langchain-community + pypdf）逐页加载；
  - .docx：`Docx2txtLoader`（langchain-community + docx2txt）；
  - .md：`TextLoader`（UTF-8、零额外依赖）；替代方案 `UnstructuredMarkdownLoader` 因依赖重且 Windows 需额外 `python-magic-bin`（见 Context）不采用。
  - loader 输出拼接为全文；有效文本长度低于阈值（默认 20 字符）→ 失败，提示「未提取到有效文本（暂不支持扫描版 PDF）」。
- **分块（langchain-text-splitters）**：`RecursiveCharacterTextSplitter(length_function=len, chunk_size=kb_chunk_size, chunk_overlap=kb_chunk_overlap)`；默认分隔符按 `段间空行 → 换行 → 空格 → 字符` 递归，对中文按字符粒度兜底切分。替代方案：自研分块器（否决：用户选型明确用 LangChain 内置组件，组件行为成熟且有测试保障）。
- **向量化**：`text-embedding-v4`；批量控制在 `embedding_batch_size`（默认 10，对齐官方单请求上限；langchain-openai 内部按 `chunk_size` 分批）；500 字/块的 token 量（约 750）远低于单行 8192 限制；单批失败轻试重试 1 次，仍失败 → 文档处理失败（可读原因 + 日志）。
- **步骤与状态**：steps 五步——解析文档 → 文本分块（含块数）→ 向量化（含 i/N 进度）→ 写入向量库 → 完成；每次更新独立短会话（对齐 `make_step_writer` 的 upsert 语义，但直接更新 documents 行）。
- **线程模型**：独立线程池（`doc_service` 模块级，并发 `doc_worker_concurrency` 默认 1）——不占生成任务的线程池（生成任务是用户可感知等待的前台流程）；文档处理串行可接受（后台）。
- **启动兜底**：`mark_stale_documents_failed()`（对齐 `mark_stale_tasks_failed`）：残留 processing → failed（「处理中断，请重新上传」）。

### D4. Embedding：LangChain `OpenAIEmbeddings` 对接百炼（`app/llm/embedding.py` 工厂）

- `build_embeddings()` 返回配置好的 `OpenAIEmbeddings(model=text-embedding-v4, base_url=dashscope_base_url, api_key=dashscope_api_key, dimensions=1024, check_embedding_ctx_length=False)`；`check_embedding_ctx_length=False` 为对接非 OpenAI 端点必须（原样发送文本，避免本地 tiktoken 分词）。
- 相似度空间：Chroma collection 采用 cosine（距离 = 1 - 余弦相似度，与向量模长无关，无需手动归一化）；`kb_similarity_threshold` 语义 = cosine 距离上限。**已实测标定（2026-10-07，scripts/calibrate_kb.py）**：相关查询距离 [0.20, 0.45]、无关查询距离 ≥0.71（单文档样本）→ 默认值定为 **0.58**（两类间中间值，两侧各留 ~0.13 余量）；样本扩充后可复测。
- 维度：默认 1024（v4 默认，质量/成本平衡）；变更维度需重建向量库（文档化警示）。
- 替代方案：自研 openai SDK 封装（否决：用户选型明确用 LangChain 内置组件；`OpenAIEmbeddings` 自带重试/批处理/异步生态）。

### D5. 检索与 Agent 工具：`RunnableConfig` 注入 user_id + 二态 Agent 缓存

- **检索器**（`app/services/kb_retriever.py`）：`search_knowledge_base(user_id, query) -> list[KbHit]`（KbHit：text / filename / doc_id / distance）；流程 = 取用户 collection（不存在 → 返回空）→ `similarity_search_with_score(query, k=kb_top_k)`（cosine 距离）→ 距离过滤（≤阈值）→ 返回。空库 / 无命中 → 空列表（不返回噪声）。
- **Agent 工具**（`kb_search`，描述见提示词）：用 `RunnableConfig` 注入读取 `config["configurable"]["user_id"]`（**机制已实测验证**）；工具内异常捕获 → 返回可读字符串（「资料库暂时不可用」），不向上抛（Agent 层自然降级，联网补位）；单条命中文本按 `kb_snippet_max_chars`（默认 1200）截断、总长受限，防上下文膨胀。
- **工具注入（二态缓存）**：Agent 进程级缓存改为按「是否含资料库工具」两个变体分别缓存；每次出题先查该用户是否有 ready 文档（1 次轻查询）→ 选择变体。满足「无就绪文档 → 行为与升级前一致、不出现资料库步骤」的规格要求；替代方案「固定工具集 + 运行时返回空」（否决：会产生无意义的资料库步骤）；「每请求重建 Agent」（否决：破坏缓存模式，且构建成本换来的是同样效果）。
- **提示词 v2**（`agent_prompt.py`）：新增资料库工具说明与路由策略——「先查资料库（如可用）：命中高相关内容优先采用；资料库没有相关内容或结果不足时，用联网搜索补充/兜底；不要反复调用给不出结果的工具」；输出格式保持（领域判断 + 要点 + 来源清单），来源清单要求区分《文档名》与「标题+链接」。
- **步骤标签**：`TOOL_STEP_LABELS` 增加 `kb_search: "资料库检索"`。
- **待端到端验证**：`create_agent` / `ToolNode` 对 `configurable` 的传播（裸调 ToolNode 缺 LangGraph 运行时上下文，故无法离线复现；列入实施任务 T1）。备选方案：`contextvars`（在任务线程包裹层 set/reset，工具闭包读取）——不改变外部行为。

### D6. 编排与契约扩展：有效内容判定、来源类型、溯源统计

- `acquire_knowledge` 签名扩展 `user_id`；`KnowledgeResult.sources` 条目增加 `type`（`web` / `library`）；`trace` 增加 `library_search_count` / `library_hit_count`。
- **有效内容判定**：`kb_search` 工具消息中解析命中片段（长度 ≥ 阈值）→ `has_valid_content=True`（资料库命中同样免除知识盲区评估，与 guardrails 规格「存在高相关资料时不误报」一致）。
- **来源模型**（`QuizSource`）：增加 `type: str = "web"`；`url` 改为可选（资料库来源无链接，携带文档名）。旧任务结果无 `type` 字段 → 默认按 web 展示（向后兼容）。
- **启用判定**：`is_enabled(user_id)` → 联网凭据已配置 **或**（百炼已配置且该用户有 ready 文档）——纯资料库场景（无 Tavily）也可走 Agent 流程。
- **降级矩阵**：

| 状态 | 上传文档 | 出题行为 |
| --- | --- | --- |
| 无 DASHSCOPE_API_KEY | 拒绝并提示未启用 | 与现状一致（纯联网或纯模型） |
| 有 key / 未登录 | 拒绝（需登录） | 匿名出题与现状一致 |
| 有 key / 登录 / 无文档 | 可上传 | 与现状一致 |
| 有 key / 有 ready 文档 / 无 Tavily | 可上传 | Agent 仅用资料库工具；无命中 → 按无资料流程（守卫评估） |
| 全配置 | 可上传 | Agent 自主路由（资料库 + 联网） |
| 资料库运行时异常 | — | 工具返回不可用 → 联网补位 → 仍不行按无资料；任务不失败 |

### D7. 前端：新增「我的资料库」页，生成页适配来源类型

- **pages/library（我的资料库）**：列表卡片（文件名 / 大小 / 状态标签 / 时间 / 失败原因 / 删除）+ 上传按钮 + 空状态引导；含 pending / processing 时以 2s 间隔轮询列表（离开页面即停，复用 generating 页的 alive 模式）。
- **上传渠道适配**：微信端 `Taro.chooseMessageFile`（count:1, type:'file', extension:['pdf','docx','md']，平台限制：从聊天记录选择）；H5 端条件编译渲染 `<input type="file">`；统一 `Taro.uploadFile`（multipart，带 Authorization；小程序 60s 上限内，20MB 限制下本地 / 局域网安全）。前端上传前做格式 / 大小预校验（提示友好），后端仍做权威校验。
- **入口**：`pages/profile` 工具箱「知识库」占位改为「资料库」启用跳转（命名决策：本次功能叫「资料库」，避免与规划中的历史闯关列表「知识库 E02」混淆；页面标题「我的资料库」）。
- **generating 页**：来源卡片按 `type` 分型展示（📄 资料库文档名 vs 🔗 联网标题+链接）；步骤流无需改动（步骤由后端标签驱动，自动出现「资料库检索」）。
- **types / api.ts**：`QuizSource` 类型更新（type + url 可选）；新增 `DocItem` 类型与 `listDocuments / uploadDocument / deleteDocument`。

### D8. 配置与依赖

- 新增配置（`core/config.py` + `.env.example` 注释）：`dashscope_api_key`（★用户自填）、`dashscope_base_url`（默认旧域名）、`embedding_model`（text-embedding-v4）、`embedding_dimensions`（1024）、`embedding_batch_size`（10）、`chroma_dir` / `upload_dir`（默认 backend/data/ 下）、`upload_max_size_mb`（20）、`kb_top_k`（5）、`kb_similarity_threshold`（0.45，cosine 距离，待标定）、`kb_chunk_size`（500）、`kb_chunk_overlap`（50）、`kb_snippet_max_chars`（1200）、`doc_worker_concurrency`（1）。
- 依赖（requirements.txt）：`langchain-community>=0.4` / `langchain-text-splitters>=1.1` / `langchain-chroma>=1.1` / `chromadb>=1.5` / `pypdf>=6.0` / `docx2txt>=0.9`（已验证 Python 3.14 全树可装）。
- 测试策略：解析层用程序化生成的小样本 fixture（pypdf/python-docx 可生成文件，走真实 loader——仅本地磁盘无网络）；Embedding 用 langchain-core 确定性 Fake（`DeterministicFakeEmbedding` 或自定义）注入；Chroma 用临时目录真实实例（本地磁盘）；Agent 端到端用自定义 FakeChatModel（实现 `bind_tools` + 预置 tool_call 序列——现有 FakeMessagesListChatModel 不支持 `bind_tools`，需在 conftest 新增）；不触真实 API。

## Risks / Trade-offs

- [阈值标定样本有限] → 已完成首轮实测标定（相关 ≤0.45 / 无关 ≥0.71 → 默认 0.58）；当前基于单文档样本，更多文档类型（PDF/Word、长文档）上线前可复跑 scripts/calibrate_kb.py 复测；配置化可热调。
- [百炼限流 / 免费额度耗尽] → 批次控制 + 重试 1 次；文档级失败可见可重传；额度耗尽表现为处理失败（非静默降级）。
- [chromadb / langchain-chroma 运行时兼容 —— **已实测通过（2026-10-07 T2 冒烟，脚本 scripts/check_chroma_smoke.py）**] → 实测结论：cosine 空间下 `similarity_search_with_score` 的 score = **1 - 余弦相似度**（同向 0.000000 / 正交 1.000000，供阈值标定）；langchain-chroma 1.1.0 删除接口用 `store.delete(where={...})`（注意与线上文档示例 `filter=` 不同，已兼容验证）；重启（子进程）后数据可查、删除不可见。真实百炼 embedding 亦已实测通过（scripts/check_dashscope.py，0.3s/单条）。
- [langchain-community 被官方标记 deprecated] → loaders 仍为官方文档推荐路径且版本活跃（0.4.2）；锁定版本下限 + 测试兜底；如未来官方迁移独立包，仅影响解析层（可替换）。
- [Agent config 传播端到端未验证] → 实施 T1 前置验证；失败即切 contextvars 备选（不影响外部契约）。
- [chromadb 传递依赖较重（kubernetes / grpcio / onnxruntime 等）] → 接受（用户指定 Chroma；本地 PersistentClient 运行时不依赖 k8s 路径）；如需瘦身另开变更。
- [PDF 解析质量参差（双栏 / 表格 / 公式）] → 第一版接受文本层提取精度；失败给可读提示；后续可升级解析器（不改变外部契约）。
- [中英文混排分块边界] → LangChain 分隔符递归 + 重叠缓解；参数可配；标定时观察样本切分质量。
- [删除与处理竞态] → 后台任务写前复查记录存在性（防残留向量）。
- [微信端选文件渠道受限（聊天记录选择）] → 产品已知限制，前端文案引导（「先把文件发到文件传输助手」）；H5 不受限。

## Migration Plan

1. 安装新依赖（`pip install -r requirements.txt`）；验证 `import chromadb, langchain_chroma, langchain_text_splitters` 与 `PyPDFLoader / Docx2txtLoader / TextLoader` 导入成功。
2. `.env` 增补 `DASHSCOPE_API_KEY`（用户自填；`.env.example` 同步增注释）。
3. 建表：`init_db()` 创建 `documents`。
4. 启动服务：自动创建 `backend/data/` 目录；启动兜底标记残留 processing 文档。
5. 回归：现有 152 测试全绿 + 新增测试通过；手动冒烟（H5 上传 → 轮询 → 出题引用资料）。
6. 回滚：清空 `DASHSCOPE_API_KEY` → 上传入口提示未启用、出题回到现状（不删表不删目录，无破坏性）；代码级回滚 `git revert`。

## Open Questions

- `kb_similarity_threshold` 最终值与分块参数组合（实施标定后确定默认值）。
- 是否需要对单用户文档数量设置上限（防滥用；当前不限制，按需再加，不影响架构）。
- 文档处理失败的一键重试入口是否值得做（第一版删除重传；如体验差再补）。
