# 烟草智能客服系统

基于 RAG（检索增强生成）的烟草行业智能客服系统，支持知识库问答、多轮对话、意图路由。

## 技术栈

| 层面 | 选型 |
|------|------|
| 后端 | FastAPI + aiosqlite |
| 前端 | React + TypeScript + Vite |
| LLM | Ollama tobacco-csa:latest（本地微调模型） |
| Embedding | DashScope text-embedding-v4（1024 维） |
| Reranker | DashScope qwen3-rerank |
| 向量库 | ChromaDB |
| 文档解析 | markitdown（默认）+ MinerU（兜底） |

## 项目结构

```
├── backend/                # 后端服务
│   ├── app/
│   │   ├── api/            # 接口层（chat、knowledge、stats）
│   │   ├── services/       # 业务层（RAG、LLM、压缩、文档处理）
│   │   ├── db/             # 数据库（SQLite）
│   │   └── models/         # Pydantic 模型
│   ├── tests/              # 测试
│   └── pyproject.toml
├── frontend/               # 前端应用
│   ├── src/
│   │   ├── api/            # API 调用层
│   │   ├── components/     # UI 组件
│   │   └── styles/         # 样式令牌
│   └── package.json
└── Docs/                   # 项目文档（PRD、API、设计文档、测试报告）
```

## 快速启动

### 后端

```bash
cd backend

# 安装依赖（需要 uv）
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 DASHSCOPE_API_KEY 和 MINERU_TOKEN

# 启动服务
uv run uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 本地 LLM

需要先安装 [Ollama](https://ollama.com/) 并拉取微调模型：

```bash
ollama pull tobacco-csa:latest
```

## 核心功能

- **RAG 知识问答** — 上传文档自动解析、分块、向量化，基于语义检索 + 精排生成回答
- **意图路由** — LLM 自动判断问题类型，烟草知识走 RAG，闲聊直接回答
- **多轮对话** — 支持上下文保持、历史会话管理
- **知识库管理** — 支持 PDF/Word/Markdown/HTML/图片上传，实时状态推送
- **统计面板** — 对话量、知识库命中率、热门问题分析
