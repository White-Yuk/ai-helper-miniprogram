# Backend · AI学习助手

FastAPI + LangChain + DeepSeek 后端服务（MVP）。

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖（Windows）
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

# 2. 配置密钥：复制 .env.example 为 .env，填入你的 DEEPSEEK_API_KEY
#    （可选：填入 DASHSCOPE_API_KEY 启用 RAG 资料库，见下文）
cp .env.example .env

# 3. 启动服务
.venv/Scripts/uvicorn app.main:app --reload --port 8000
```

接口文档（Swagger）：http://127.0.0.1:8000/docs

## 测试（TDD）

```bash
.venv/Scripts/pytest
```

测试中 LLM 全部使用 Mock，不消耗真实 API 额度。

## 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/api/v1/health`          | 健康检查 |
| POST | `/api/v1/quiz/generate`   | 生成闯关题库（同步接口；H5 / 调试 / 兼容场景） |
| POST | `/api/v1/quiz/tasks`      | 创建生成任务，立即返回 task_id（小程序端生成流程） |
| GET  | `/api/v1/quiz/tasks/{task_id}` | 查询任务状态 / 步骤 / 结果 / 错误 |
| POST | `/api/v1/report/generate` | 生成复盘报告 |
| POST | `/api/v1/documents` | 上传文档（multipart；受理后后台处理，需登录） |
| GET  | `/api/v1/documents` | 我的文档列表（含处理状态与步骤，供轮询） |
| DELETE | `/api/v1/documents/{doc_id}` | 删除文档（记录 + 向量 + 原文件） |

## 异步生成任务（小程序端生成流程）

背景：微信小程序 `wx.request` 的最大超时时间为 **60 秒（硬性上限，超出会被静默截断为 60s）**，而“联网检索 + 出题”的单次生成耗时无法保证 60s 内完成，因此生成流程采用【异步任务 + 轮询】：

1. `POST /api/v1/quiz/tasks` 创建任务（立即返回 `task_id`，状态 `pending`）；
2. 客户端定时轮询 `GET /api/v1/quiz/tasks/{task_id}`，实时渲染步骤（搜索 → 找到资料 → 深读 / 提取 → 研判 → 出题）；
3. 任务终态：`done` 获取题目结果与来源（`sources` / `agent_trace`）；`failed` 按 `error.code` 展示（如 4006 知识盲区，引导补充资料或更换主题）。

任务持久化在数据库 `generation_tasks` 表（建表：`.venv/Scripts/python.exe -c "from app.core.db import init_db; init_db()"`）：服务重启后已存在的任务仍可查询；服务启动时会把残留的 `running` 任务标记为 `failed`，避免客户端无限轮询。

同步接口 `POST /api/v1/quiz/generate` 保留且行为不变（仅供 H5 / 调试 / 兼容场景），小程序端不再调用。

## 知识获取增强（Tavily 联网检索，可选）

1. 获取 Key：https://app.tavily.com → API Keys（`tvly-` 开头；免费额度以官网为准）；
2. 在 `.env` 填写 `TAVILY_API_KEY=...`（其余调优项均有默认值，见 `.env.example`）；
3. 重启后端生效。启用后，出题前由 AI Agent 联网检索 / 提取网页内容作为出题依据（超出模型训练数据的新概念也能出对题）；出题结果携带来源（`sources`）与知识溯源（`agent_trace`）。

**回滚**：清空 `TAVILY_API_KEY` 即回到纯模型知识出题，行为与升级前完全一致。

**失败自动降级**：检索网络异常 / 超时 / 限流时不会导致生成失败，系统自动降级为无资料模式继续处理（或按知识盲区守卫输出 4006 引导）。

## RAG 资料库（文档上传 → 出题检索增强，可选）

把用户自己的学习资料（PDF / Word / Markdown）向量化存入本地 Chroma 向量库；出题时 AI Agent 会**先检索资料库**（命中优先采用），资料不足再联网搜索补充。

**启用步骤**：

1. 获取 Key：https://bailian.console.aliyun.com → API-KEY 管理（阿里云百炼，新用户有免费额度）；
2. 在 `.env` 填写 `DASHSCOPE_API_KEY=...`（其余调优项均有默认值，见 `.env.example`）；
3. 重启后端生效。

**使用方式**（前端「我的 → 资料库」页）：

- 小程序端：先把文件发到微信「文件传输助手」，再从聊天记录选择上传（平台限制，无法直接浏览手机文件）；
- H5 / 浏览器端：直接选择本地文件；
- 限制：PDF / `.docx` / `.md`，单文件 ≤ 20MB；不支持扫描版 PDF（无 OCR）与旧版 `.doc`。

上传后文档进入后台处理（解析 → 分块 → 向量化 → 入库），前端每 2s 轮询状态直至「已就绪」；出题结果会携带资料库来源（`sources` 中 `type="library"` 的条目）与检索统计（`agent_trace.library_search_count`）。

**回滚**：清空 `DASHSCOPE_API_KEY` → 上传入口提示未启用，出题行为与升级前完全一致（不影响任何现有功能）。

**数据位置**（不入版本库）：原文件 `backend/data/uploads/{user_id}/`、向量库 `backend/data/chroma/`（每用户一个 collection `kb_{user_id}`，cosine 空间）。

**运维脚本**（backend 目录）：

```bash
.venv/Scripts/python.exe scripts/check_dashscope.py    # 百炼连通性检查
.venv/Scripts/python.exe scripts/check_chroma_smoke.py # 向量库冒烟（cosine 距离语义 / 持久化）
.venv/Scripts/python.exe scripts/calibrate_kb.py       # 检索阈值实测标定（相关/无关距离分布）
```

**检索阈值**：`kb_similarity_threshold` 默认 0.58（cosine 距离上限），2026-10-07 实测标定：相关查询 ≤0.45、无关查询 ≥0.71；文档类型扩充后可复跑 `calibrate_kb.py` 复测。
