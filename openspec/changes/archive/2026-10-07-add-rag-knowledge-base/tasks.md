# Tasks

## 1. 技术前置验证与依赖

- [x] 1.1 更新 `requirements.txt` 并安装依赖（langchain-community / langchain-text-splitters / langchain-chroma / chromadb / pypdf / docx2txt），验证：`pip install -r requirements.txt` 成功且 `python -c "import chromadb, langchain_chroma, langchain_text_splitters; from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader, TextLoader"` 无报错
- [x] 1.2 前置验证 T1：写临时脚本验证 `create_agent`/`ToolNode` 将 `config={"configurable":{"user_id":...}}` 传播到工具（自定义 FakeChatModel 实现 `bind_tools` + 预置 tool_call 序列），验证：脚本断言工具内读到的 user_id 与调用一致；若失败改用 contextvars 备选方案并同步更新 design.md 决策记录
- [x] 1.3 前置验证 T2：Chromadb + langchain-chroma 冒烟（Python 3.14 / Windows）——通过 langchain-chroma 创建带 cosine 空间的持久化 collection（模拟 `kb_{user_id}`）、写入自定义嵌入、`similarity_search_with_score` 查询、按 where 删除、重启进程后数据仍可查；**确认 similarity_search_with_score 的距离语义**（写入 design 风险记录，供阈值标定参考），验证：冒烟脚本全部步骤通过并输出观察记录

## 2. 配置与数据模型

- [x] 2.1 在 `core/config.py` 新增配置项（dashscope_api_key / dashscope_base_url / embedding_model / embedding_dimensions / embedding_batch_size / chroma_dir / upload_dir / upload_max_size_mb / kb_top_k / kb_similarity_threshold / kb_chunk_size / kb_chunk_overlap / kb_snippet_max_chars / doc_worker_concurrency），同步更新 `backend/.env.example`（含注释与默认值说明），验证：`python -c "from app.core.config import get_settings; print(get_settings().embedding_model)"` 输出 text-embedding-v4
- [x] 2.2 新增 `models/document.py`（documents 表，字段对齐 design D2）并注册进 `models/__init__.py` 与 `init_db`，`backend/data/` 加入 .gitignore，验证：`init_db()` 后 documents 表存在（`scripts/check_db.py` 或测试）
- [x] 2.3 新增模型与建表测试 `tests/test_document_model.py`（字段默认值、状态枚举约束、user_id 索引），验证：pytest 通过

## 3. Embedding 封装与文本处理（单元）

- [x] 3.1 新增 `llm/embedding.py`（LangChain `OpenAIEmbeddings` 工厂：百炼 base_url / model / dimensions / `check_embedding_ctx_length=False`；未配置时抛可识别异常）+ `tests/test_embedding.py`（断害构造参数正确、未配置行为；不触网），验证：pytest 通过
- [x] 3.2 新增 `utils/text_splitter.py`（LangChain `RecursiveCharacterTextSplitter` 工厂，参数来自配置）+ `tests/test_text_splitter.py`（中文段落 / 超长单段 / 重叠正确性 / 空输入；参数与配置一致），验证：pytest 通过
- [x] 3.3 新增 `utils/doc_parser.py`（按文件类型选择 LangChain loader：PyPDFLoader / Docx2txtLoader / TextLoader；输出全文 + 有效文本阈值检测）+ `tests/test_doc_parser.py`（程序化生成小样本文件走真实 loader；空文本与格式分支），验证：pytest 通过

## 4. 文档服务与接口（离线建库链路）

- [x] 4.1 新增 `services/vector_store.py`（langchain-chroma 封装：持久化 client 单例、每用户 collection（`kb_{user_id}`，cosine）、add_chunks / delete_by_doc / search 封装，支持测试注入临时目录）+ `tests/test_vector_store.py`（写入 / 相似度查询 / 按 doc_id 删除 / 用户 collection 隔离），验证：pytest 通过
- [x] 4.2 新增 `services/doc_service.py`（上传校验与落盘、创建记录、独立线程池处理流水线：loader 解析→splitter 分块→embedding→向量入库、steps 与状态机更新、失败兜底、删除清理与处理竞态防护、启动兜底 `mark_stale_documents_failed`）+ `tests/test_doc_service.py`（Fake embedding / 临时 Chroma：状态流转、步骤内容、失败路径、删除竞态丢弃、启动兜底），验证：pytest 通过
- [x] 4.3 新增 `api/v1/routes/documents.py`（POST 上传 multipart / GET 列表 / DELETE 删除；登录鉴权；格式与大小校验错误码）+ `tests/test_documents_api.py`（上传受理 / 未登录 4003 / 格式与大小拒绝 4000 / 列表 / 删除 / 越权 4005），验证：pytest 通过
- [x] 4.4 注册路由与启动兜底（`api/v1/router.py`、`main.py` 的 lifespan 调用 `mark_stale_documents_failed`），验证：uvicorn 启动成功且 `GET /api/v1/documents` 未登录返回 4003；pytest 全量通过

## 5. 检索器与 Agent 改造（在线链路）

- [x] 5.1 新增 `services/kb_retriever.py`（用户 collection → `similarity_search_with_score` → cosine 距离阈值过滤 → KbHit 列表；空库与无命中返回空）+ `tests/test_kb_retriever.py`（Fake embedding + 临时 Chroma：命中排序 / 阈值过滤 / 用户 collection 隔离 / 未就绪文档无向量故不出现），验证：pytest 通过
- [x] 5.2 改造 `services/knowledge_agent.py`：新增 `kb_search` 工具（RunnableConfig 读 user_id、异常转可读字符串、片段截断）、按「含/不含资料库工具」二态缓存 Agent、`TOOL_STEP_LABELS` 增加「资料库检索」、`_parse_agent_result` 解析资料库来源与统计、`acquire_knowledge(user_input, user_id, on_step)` + `tests/test_knowledge_agent_kb.py`（工具注册条件 / 来源解析 / 库异常降级 / 无文档不注入），验证：pytest 通过
- [x] 5.3 更新 `prompts/agent_prompt.py`（v2：资料库工具说明、先库后网路由策略、来源区分）+ 更新 `tests/test_prompt_contract.py`（新增断言），验证：pytest 通过
- [x] 5.4 改造 `services/quiz_service.py` 编排：`is_enabled(user_id)` 扩展（联网凭据或资料库可用）、有效内容判定涵盖资料库命中、来源合并与 trace 扩展 + `tests/test_quiz_service_rag.py`（资料库命中免除盲区 / 无文档行为与现状一致 / 资料库异常降级联网 / 来源类型正确），验证：pytest 通过
- [x] 5.5 传递 user_id：`routes/quiz.py` 同步接口与 `task_service._execute_generation` 调用链传入用户标识 + 更新受影响测试，验证：pytest 全量通过（含既有 152 用例回归）
- [x] 5.6 扩展 `models/quiz.py` 的 `QuizSource`（type 默认 web、url 可选）与相关 schema 测试，验证：pytest 通过且旧结果反序列化兼容

## 6. 前端（资料库页与生成页适配）

- [x] 6.1 更新 `front/src/types/index.ts`（QuizSource 增 type / url 可选；新增 DocItem 等）与 `services/api.ts`（listDocuments / uploadDocument / deleteDocument），验证：`npm run build:weapp` 构建无类型错误
- [x] 6.2 新增 `pages/library`（我的资料库：列表卡片 / 状态标签 / 失败原因 / 删除 / 上传按钮 / 空态引导 / 处理中 2s 轮询）并在 `app.config.ts` 注册，验证：H5 打开 `#/pages/library/index` 页面渲染正常、上传与轮询可用
- [x] 6.3 启用 `pages/profile` 工具箱「资料库」入口（跳转资料库页）；`pages/generating` 来源卡片按 type 分型（📄 文档名 / 🔗 联网链接）展示，验证：H5 走查入口跳转正确、来源卡片两种形态渲染正确
- [x] 6.4 双端上传渠道实现（weapp `chooseMessageFile` / H5 `input[type=file]` 条件编译 + 前端预校验），验证：H5 端上传成功；微信开发者工具模拟选择文件上传成功

## 7. 集成验收

- [x] 7.1 真实链路冒烟（H5）：上传 PDF / docx / md 各一份真实文档 → 全部 ready → 出题输入与文档相关主题，验证：任务步骤流出现「资料库检索」、来源卡片含资料库条目、题目基于文档内容
- [x] 7.2 检索参数标定：构造相关 / 无关查询样本测量 cosine 距离分布，确定 `kb_similarity_threshold` 默认值与分块参数并更新配置与文档，验证：无关查询被滤除、相关查询可命中（记录数据）
- [x] 7.3 降级矩阵全场景验证（无 DASHSCOPE key / 未登录 / 无文档 / 无 Tavily / 资料库异常注入），验证：各场景行为符合 design D6 矩阵且任务不失败
- [x] 7.4 微信端全流程验证（真机或开发者工具）：从聊天记录选文件上传 → 轮询状态 → 出题命中资料，验证：全流程可用且无 60s 超时问题
- [x] 7.5 更新 `backend/README.md`（资料库配置项、依赖安装、使用说明）与 `.env.example` 终稿检查，验证：按文档步骤从零配置可复现（新人视角走查）
- [x] 7.6 空响应加固（7.4 验证中发现）：出题链检测空响应（DeepSeek V4.1 Flash 偶发 HTTP 200 无 tool_calls）→ 退避重试 + 连续空响应切换 `json_mode` 异构兜底链，验证：5 个新增单测 + 真实链路闭环（主链持续空响应 → json_mode 兜底成功）通过
