# Proposal

## Why

现状出题系统只能通过联网检索（Tavily）获取外部资料，无法利用用户自己的学习材料（课程讲义、考研资料、企业文档等）——用户上传了自己的资料，出题却仍只围绕互联网通用内容。用户明确要求补齐「离线建库」能力：上传 PDF / Word / Markdown 文档 → 解析 → 分块 → Embedding 向量化 → 存入 Chroma 向量数据库；并让出题链路的 AI Agent 具备「智能路由」——自主判断是走资料库检索还是联网搜索。

经人工确认的范围收敛：本次**不做**独立问答 / 生成回答功能（推迟到后续版本）；知识库为**单库**形态（一个「我的资料库」）；Embedding 采用**阿里云百炼 text-embedding-v4**；上传限制：PDF / .docx / .md、≤20MB、不支持扫描版 PDF（无 OCR）与旧版 .doc。

## What Changes

- **离线建库（新增）**：用户上传 PDF / .docx / .md（微信端从聊天记录选文件、H5 端直接选文件），后台异步处理（解析 → 分块 → 百炼向量化 → Chroma 持久化），处理进度可见（步骤流）；「我的资料库」页管理文档（列表 / 处理后状态 / 失败原因 / 删除）；文档严格按用户隔离。
- **出题 Agent 自主路由（修改）**：出题 Agent 新增「资料库检索」工具，与现有 Tavily 联网工具并存，由 Agent 自主判断查资料库还是联网搜索；提示词规定「资料库有相关内容时优先采用」。资料库命中的资料与联网资料均可注入出题 Prompt。
- **有效内容判定与来源扩展（修改）**：资料库命中有效片段同样视为「获取成功」（不再触发知识盲区评估）；来源列表新增资料库文档条目（来源卡片区分「我的资料」与「联网」）；生成任务步骤流新增「资料库检索」步骤类型。
- **配置与依赖（新增）**：新增 `DASHSCOPE_API_KEY` 等百炼配置项（.env）；新增依赖 LangChain 组件（langchain-community / langchain-text-splitters / langchain-chroma）与 chromadb / pypdf / docx2txt；新增 Chroma 持久化目录与上传文件存储目录。

**范围外（经人工确认）**：独立问答 / 生成回答功能（推迟）；多知识库 / 文件夹管理（先做单库）；扫描版 PDF 无文本提取（无 OCR）；旧版 .doc 格式；文档在线预览。

## Capabilities

### New Capabilities

- `doc-knowledge-base`: 文档知识库能力——用户文档上传（格式 / 大小校验、双端选择渠道）、异步解析分块处理（状态机与进度可见）、向量化入库（百炼 text-embedding-v4 → Chroma）、文档管理（列表 / 删除 / 失败处理）、用户隔离、面向 Agent 的相似度检索行为。

### Modified Capabilities

- `quiz-search-grounding`: 「智能知识获取」从「联网搜索」扩展为「Agent 自主路由」——新增资料库检索工具（用户有就绪文档时才注入）、资料库命中计入有效内容判定、来源列表覆盖资料库文档；生成任务步骤流新增「资料库检索」步骤。

## Impact

- **后端**：新增 `models/document.py`、`services/doc_service.py`（处理流水线）、`llm/embedding.py`（LangChain OpenAIEmbeddings 对接百炼）、`services/kb_retriever.py`（相似度检索）；新增 `routes/documents.py`；改造 `services/knowledge_agent.py`（新工具 + user_id 上下文传递）、`services/quiz_service.py`（有效内容判定 / 来源合并）、`api/v1/routes/quiz.py`（user_id 传递）、`core/config.py`（新增百炼与知识库配置）；`requirements.txt` 新增依赖（langchain-community / langchain-text-splitters / langchain-chroma / chromadb / pypdf / docx2txt）。
- **前端**：新增 `pages/library`（我的资料库：上传 / 列表 / 轮询 / 删除）；`pages/profile` 启用「知识库」入口；`pages/generating` 步骤流与溯源卡片适配资料来源类型；`types`、`api.ts`、`app.config.ts` 同步更新。
- **数据**：新增 `documents` 表；新增 Chroma 持久化目录与上传文件目录（均不提交版本库）。
- **兼容与降级**：未配置百炼 key / 未登录 / 无可检索文档 → 全部路径保持与现状一致（纯联网或纯模型出题），现有 150+ 测试保持全绿；现有 API 契约向后兼容（来源字段为增量扩展）。
