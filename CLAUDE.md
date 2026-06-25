# 烟草智能客服系统 — 项目规范

## 项目概述

基于 Mimo-v2.5 + RAG 的烟草行业智能客服系统。后端 FastAPI，前端 React，向量库 ChromaDB，部署 Docker Compose。

## 技术栈

| 层面 | 选型 | 说明 |
|------|------|------|
| 语言 | Python 3.11+ | uv 管理 |
| 后端 | FastAPI | 异步框架 |
| LLM | Mimo-v2.5 | OpenAI 兼容 API |
| RAG | LangChain + ChromaDB + bge-large-zh-v1.5 + bge-reranker-v2-m3 | 本地 Embedding + Reranker |
| 文档解析 | MinerU | PDF/Word/图片 → Markdown |
| 前端 | React + Vite | ChatGPT 风格 |
| 数据库 | SQLite | aiosqlite 异步 |
| 部署 | Docker Compose | |

## 环境管理

```bash
# 初始化项目
uv init

# 添加依赖（自动写入 pyproject.toml + uv.lock）
uv add fastapi uvicorn aiosqlite
uv add langchain langchain-community chromadb
uv add sentence-transformers
uv add openai httpx
uv add python-multipart

# 运行
uv run uvicorn app.main:app --reload

# 一次性脚本
uv run --with <pkg> script.py
```

**禁止：**
- ❌ `pip install`
- ❌ `source .venv/bin/activate`
- ❌ `requirements.txt`
- ❌ `python -m venv`

## 代码规范

### 文件结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口，挂载路由、CORS、启动事件
│   ├── config.py            # 配置项（从环境变量读取）
│   ├── api/
│   │   ├── chat.py          # 对话接口
│   │   ├── knowledge.py     # 知识库接口
│   │   └── stats.py         # 统计接口
│   ├── services/
│   │   ├── llm_service.py   # LLM 调用封装
│   │   ├── rag_service.py   # RAG 检索 + 精排
│   │   ├── chat_service.py  # 对话编排
│   │   ├── compression.py   # 上下文压缩
│   │   ├── knowledge.py     # 文档处理
│   │   └── stats_service.py # 统计查询
│   ├── models/
│   │   └── schemas.py       # Pydantic 模型
│   ├── db/
│   │   ├── database.py      # SQLite 连接管理
│   │   └── init.sql         # 建表脚本
│   └── utils/
│       └── helpers.py       # 工具函数
├── data/
│   ├── raw/                 # 原始上传文件
│   ├── processed/           # MinerU 解析后的 Markdown
│   └── chroma/              # ChromaDB 持久化
└── pyproject.toml
```

### 命名规范

- **文件名**：`snake_case.py`
- **类名**：`PascalCase`（如 `ChatService`）
- **函数/变量**：`snake_case`（如 `build_messages`、`rag_results`）
- **常量**：`UPPER_SNAKE_CASE`（如 `RAG_TOP_K`）
- **私有成员**：`_leading_underscore`（如 `_compress_session`）

### 代码风格

```python
# ✅ 好的写法
async def build_messages(
    session_id: str,
    user_message: str,
    rag_results: list[dict],
) -> list[dict]:
    """组装发送给 LLM 的 messages 数组。"""
    # 构建 system message：角色设定 + RAG 内容 + 压缩摘要
    system_parts = [ROLE_PROMPT]
    system_parts.append(_format_rag_results(rag_results))
    system_parts.extend(_get_compression_summaries(session_id))

    system_message = {"role": "system", "content": "\n\n".join(system_parts)}

    # 获取最近 15 轮对话历史
    history = await get_recent_messages(session_id, limit=15)
    history_msgs = [{"role": m.role, "content": m.content} for m in history]

    return [system_message] + history_msgs + [{"role": "user", "content": user_message}]


# ❌ 不好的写法
async def buildMsgs(sid, msg, rag):
    sp = [ROLE_PROMPT]
    sp.append(formatRAG(rag))
    sp.extend(getComp(sid))
    sm = {"role": "system", "content": "\n\n".join(sp)}
    h = await getMsgs(sid, 15)
    hm = [{"role": m.role, "content": m.content} for m in h]
    return [sm] + hm + [{"role": "user", "content": msg}]
```

### 注释规范

- **中文注释**，简洁说明意图，不解释显而易见的代码
- 函数用一行 docstring 说明用途
- 复杂逻辑在关键步骤上方加行内注释
- 不写 `# 返回结果` 这种废话注释

```python
# ✅ 好的注释
# 压缩未完成时 fallback：直接用最近 15 轮完整对话兜底
compressions = await get_compressions(session_id)

# ChromaDB metadata 不支持 list，用 JSON 字符串存储
metadata["retrieved_doc_ids"] = json.dumps(doc_ids)

# ❌ 废话注释
# 查询压缩记录
compressions = await get_compressions(session_id)

# 遍历结果
for item in results:
    ...
```

### 类型标注

- 所有函数参数和返回值必须标注类型
- 使用 Python 3.11+ 语法：`list[dict]` 而非 `List[Dict]`
- 可选类型用 `str | None` 而非 `Optional[str]`

```python
async def get_recent_messages(
    session_id: str,
    limit: int = 15,
) -> list[Message]:
    ...
```

### 错误处理

- API 层统一捕获异常，返回标准错误格式
- Service 层抛出自定义异常，不直接返回 HTTP 响应
- 异步任务（压缩、文档处理）内部 try-except，记录日志，不向用户暴露

### 异步规范

- 数据库操作用 `aiosqlite`
- HTTP 请求用 `httpx.AsyncClient`
- LLM 调用、文档处理等耗时操作用 `asyncio.create_task` 后台执行
- 不在 async 函数中调用阻塞操作（如 `time.sleep`、同步文件 IO）

## 开发流程

### 开发顺序

```
P0: 项目初始化 + LLM 调通 + 基础对话
P1: RAG 流程（MinerU 解析 → 分块 → 向量化 → 检索 → 精排 → 生成）
P2: 多轮对话 + 上下文压缩
P3: 前端三个页面
P4: 文件上传 + 数据统计
P5: Docker Compose 部署 + 联调测试
```

### 提交规范

```
feat: 新功能
fix: 修复
refactor: 重构
docs: 文档
chore: 构建/配置
```

### 分支策略

- `main` — 稳定版本
- `dev` — 开发分支
- `feat/xxx` — 功能分支

## API 规范

- 所有接口前缀：`/api`
- 成功响应：`{"code": 0, "data": {...}, "msg": "ok"}`
- 错误响应：`{"code": 4xx/5xx, "data": null, "msg": "错误描述"}`
- SSE 流式接口：`POST /api/chat`
- 详见 `Docs/API文档.md`

## 文档

所有文档在 `Docs/` 目录下：

- `PRD.md` — 产品需求文档
- `技术设计文档.md` — 整体架构、技术栈、前端、部署
- `后端详细设计.md` — 后端模块、数据结构、压缩机制
- `RAG设计文档.md` — RAG 全流程
- `API文档.md` — 前后端接口约定

## 配置管理

配置项集中在 `app/config.py`，从环境变量读取，有默认值：

```python
# LLM
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "mimo-v2.5")

# RAG
RAG_RETRIEVAL_TOP_K = int(os.getenv("RAG_RETRIEVAL_TOP_K", "20"))
RAG_RERANK_TOP_K = int(os.getenv("RAG_RERANK_TOP_K", "5"))

# 路径
DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
```

敏感信息（API Key、MinerU Token）通过 `.env` 文件注入，不提交到 git。
