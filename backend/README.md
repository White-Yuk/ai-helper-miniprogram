# Backend · AI 闯关学习

FastAPI + LangChain + DeepSeek 后端服务（MVP）。

## 快速开始

```bash
# 1. 创建虚拟环境并安装依赖（Windows）
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt

# 2. 配置密钥：复制 .env.example 为 .env，填入你的 DEEPSEEK_API_KEY
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
| POST | `/api/v1/quiz/generate`   | 生成闯关题库（题型/题量/难度可配） |
| POST | `/api/v1/report/generate` | 生成复盘报告 |
