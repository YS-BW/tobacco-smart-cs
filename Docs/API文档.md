# API 文档

> 前后端开发的唯一约定。所有接口基地址：`http://localhost:8000/api`

---

## 一、通用约定

### 1.1 请求头

| 请求头 | 值 | 说明 |
|--------|---|------|
| `Content-Type` | `application/json` | 除文件上传外的所有请求 |
| `Content-Type` | `multipart/form-data` | 文件上传 |

### 1.2 响应格式

**成功响应（非 SSE）：**

```json
{
    "code": 0,
    "data": { ... },
    "msg": "ok"
}
```

**错误响应：**

```json
{
    "code": 400,
    "data": null,
    "msg": "错误描述信息"
}
```

**HTTP 状态码：**

| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 204 | 删除成功（无响应体） |
| 400 | 请求参数错误 |
| 404 | 资源不存在 |
| 500 | 服务器内部错误 |

### 1.3 SSE 流式响应格式

对话接口使用 Server-Sent Events，响应头：`Content-Type: text/event-stream`

```
data: {"type": "references", "sources": [...]}\n\n
data: {"type": "reasoning", "text": "..."}\n\n
data: {"type": "content", "text": "..."}\n\n
data: {"type": "done", "text": ""}\n\n
```

每个 `data:` 行是一个 JSON 对象，`\n\n` 分隔不同事件。

---

## 二、数据模型定义

### 2.1 Session（会话）

```typescript
interface Session {
    id: string;              // UUID
    title: string;           // 会话标题（首条用户消息截取前20字）
    message_count: number;   // 消息轮次计数
    created_at: string;      // ISO 8601 格式
    updated_at: string;      // ISO 8601 格式
}
```

### 2.2 Message（消息）

```typescript
interface Message {
    id: number;
    session_id: string;
    role: "user" | "assistant";
    content: string;                    // 正文内容
    reasoning_content: string | null;   // 推理过程（仅 assistant，可为 null）
    references: SourceInfo[] | null;    // 引用来源（仅 assistant，可为 null）
    created_at: string;                 // ISO 8601 格式
}
```

### 2.3 SourceInfo（引用来源）

```typescript
interface SourceInfo {
    index: number;       // 编号，从 1 开始
    title: string;       // 文档标题（heading_path 最后一级标题）
    filename: string;    // 源文件名
    content: string;     // 命中的子块内容（截取前 200 字）
}
```

### 2.4 KnowledgeDoc（知识库文档）

```typescript
interface KnowledgeDoc {
    id: number;
    filename: string;                              // 文件名
    file_type: "pdf" | "word" | "image" | "markdown"; // 文件类型
    chunk_count: number;                           // 分块数量
    status: "processing" | "ready" | "failed";     // 处理状态
    created_at: string;                            // ISO 8601 格式
}
```

### 2.5 StatsOverview（统计总览）

```typescript
interface StatsOverview {
    total_sessions: number;    // 总会话数
    total_messages: number;    // 总消息数
    total_docs: number;        // 知识库文档数
    kb_hit_rate: number;       // 知识库命中率（百分比，如 78.5）
}
```

### 2.6 TopQuestion（热门问题）

```typescript
interface TopQuestion {
    question: string;   // 问题文本
    count: number;      // 出现次数
}
```

---

## 三、对话接口

### 3.1 发送消息（SSE 流式）

**`POST /api/chat`**

发送用户消息，返回 SSE 流式响应。

**请求体：**

```json
{
    "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "message": "黄鹤楼硬蓝的焦油量是多少？"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| session_id | string | 是 | 会话 ID |
| message | string | 是 | 用户消息内容 |

**响应：`Content-Type: text/event-stream`**

**事件时序：**

```
1. references 事件（RAG 检索完成后立即推送）
2. reasoning 事件 × N（LLM 推理过程，可选展示）
3. content 事件 × N（LLM 最终回答，逐字/逐句推送）
4. done 事件（本次回复结束）
```

**事件格式：**

**references 事件：**

```json
{
    "type": "references",
    "sources": [
        {
            "index": 1,
            "title": "黄鹤楼产品参数",
            "filename": "huanghelou.pdf",
            "content": "黄鹤楼（硬蓝）：焦油量10mg，烟气烟碱量1.0mg，烟气一氧化碳量11mg..."
        },
        {
            "index": 2,
            "title": "烤烟型卷烟标准",
            "filename": "standard.md",
            "content": "烤烟型卷烟是指以烤烟为主要原料..."
        }
    ]
}
```

- `sources` 为检索命中的文档列表，按精排分数降序排列
- 如果 RAG 无命中结果，`sources` 为空数组 `[]`
- 前端收到后**立即渲染**引用来源卡片，无需等待 LLM 回复

**reasoning 事件：**

```json
{"type": "reasoning", "text": "用户询问黄鹤楼硬蓝的焦油量，"}
{"type": "reasoning", "text": "让我在知识库中查找相关信息..."}
```

- `text` 为推理过程的增量文本片段
- 前端可选择展示或隐藏（折叠显示）
- 不是所有模型都有推理内容，可能为空流

**content 事件：**

```json
{"type": "content", "text": "根据"}
{"type": "content", "text": "知识库信息，"}
{"type": "content", "text": "黄鹤楼（硬蓝）的焦油量为 10mg。"}
```

- `text` 为最终回答的增量文本片段
- 前端逐字拼接展示

**done 事件：**

```json
{"type": "done", "text": ""}
```

- 标记本次回复结束
- 前端收到后停止 loading 状态，将完整回复存入本地状态

**错误情况（SSE 内推送）：**

```json
{"type": "error", "text": "模型调用超时，请重试"}
```

---

### 3.2 创建会话

**`POST /api/sessions`**

**请求体：**

```json
{
    "title": "可选的自定义标题"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 否 | 不传则默认为"新对话" |

**响应：`201 Created`**

```json
{
    "code": 0,
    "data": {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "title": "新对话",
        "message_count": 0,
        "created_at": "2025-06-25T10:00:00Z",
        "updated_at": "2025-06-25T10:00:00Z"
    },
    "msg": "ok"
}
```

---

### 3.3 获取会话列表

**`GET /api/sessions`**

按 `updated_at` 降序排列（最近活跃的在最前面）。

**响应：`200 OK`**

```json
{
    "code": 0,
    "data": [
        {
            "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "title": "黄鹤楼硬蓝的焦油量",
            "message_count": 6,
            "created_at": "2025-06-25T10:00:00Z",
            "updated_at": "2025-06-25T10:05:00Z"
        },
        {
            "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "title": "烟草专卖许可证办理流程",
            "message_count": 4,
            "created_at": "2025-06-25T09:00:00Z",
            "updated_at": "2025-06-25T09:10:00Z"
        }
    ],
    "msg": "ok"
}
```

---

### 3.4 获取会话消息历史

**`GET /api/sessions/{session_id}/messages`**

获取指定会话的所有消息，按 `created_at` 升序排列。

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| session_id | string | 会话 ID |

**响应：`200 OK`**

```json
{
    "code": 0,
    "data": [
        {
            "id": 1,
            "session_id": "a1b2c3d4-...",
            "role": "user",
            "content": "黄鹤楼硬蓝的焦油量是多少？",
            "reasoning_content": null,
            "references": null,
            "created_at": "2025-06-25T10:00:00Z"
        },
        {
            "id": 2,
            "session_id": "a1b2c3d4-...",
            "role": "assistant",
            "content": "根据知识库信息，黄鹤楼（硬蓝）的焦油量为 10mg。",
            "reasoning_content": "用户询问黄鹤楼硬蓝的焦油量...",
            "references": [
                {
                    "index": 1,
                    "title": "黄鹤楼产品参数",
                    "filename": "huanghelou.pdf",
                    "content": "焦油量10mg..."
                }
            ],
            "created_at": "2025-06-25T10:00:05Z"
        }
    ],
    "msg": "ok"
}
```

**错误：会话不存在**

```json
{
    "code": 404,
    "data": null,
    "msg": "会话不存在"
}
```

---

### 3.5 删除会话

**`DELETE /api/sessions/{session_id}`**

级联删除该会话的所有消息、压缩记录、问答日志。

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| session_id | string | 会话 ID |

**响应：`204 No Content`**（无响应体）

**错误：会话不存在**

```json
{
    "code": 404,
    "data": null,
    "msg": "会话不存在"
}
```

---

## 四、知识库接口

### 4.1 上传文档

**`POST /api/knowledge/upload`**

上传文件到知识库，系统自动解析、分块、向量化。

**请求：`multipart/form-data`**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| files | File[] | 是 | 支持多个文件，支持 pdf/doc/docx/png/jpg/jpeg/webp/md |

**支持的文件格式：**

| 格式 | 扩展名 | 处理方式 |
|------|--------|---------|
| PDF | .pdf | MinerU 解析 |
| Word | .doc, .docx | MinerU 解析 |
| 图片 | .png, .jpg, .jpeg, .webp | MinerU 解析 + OCR |
| Markdown | .md | 直接使用 |

**响应：`201 Created`**

```json
{
    "code": 0,
    "data": {
        "message": "3 个文件已提交处理",
        "docs": [
            {
                "id": 1,
                "filename": "烟草专卖法.pdf",
                "file_type": "pdf",
                "chunk_count": 0,
                "status": "processing",
                "created_at": "2025-06-25T10:00:00Z"
            },
            {
                "id": 2,
                "filename": "卷烟分类标准.docx",
                "file_type": "word",
                "chunk_count": 0,
                "status": "processing",
                "created_at": "2025-06-25T10:00:00Z"
            },
            {
                "id": 3,
                "filename": "焦油量数据.md",
                "file_type": "markdown",
                "chunk_count": 0,
                "status": "processing",
                "created_at": "2025-06-25T10:00:00Z"
            }
        ]
    },
    "msg": "ok"
}
```

**说明：**
- 上传后异步处理，`status` 初始为 `processing`
- 处理完成后 `status` 变为 `ready`，`chunk_count` 更新为实际分块数
- 处理失败则 `status` 变为 `failed`
- 前端可通过轮询 `GET /api/knowledge/documents` 查看处理进度

---

### 4.2 获取文档列表

**`GET /api/knowledge/documents`**

获取知识库中所有文档及其处理状态。按 `created_at` 降序排列。

**响应：`200 OK`**

```json
{
    "code": 0,
    "data": [
        {
            "id": 1,
            "filename": "烟草专卖法.pdf",
            "file_type": "pdf",
            "chunk_count": 45,
            "status": "ready",
            "created_at": "2025-06-25T10:00:00Z"
        },
        {
            "id": 2,
            "filename": "卷烟分类标准.docx",
            "file_type": "word",
            "chunk_count": 23,
            "status": "ready",
            "created_at": "2025-06-25T09:50:00Z"
        },
        {
            "id": 3,
            "filename": "大文件.pdf",
            "file_type": "pdf",
            "chunk_count": 0,
            "status": "processing",
            "created_at": "2025-06-25T09:40:00Z"
        },
        {
            "id": 4,
            "filename": "损坏文件.pdf",
            "file_type": "pdf",
            "chunk_count": 0,
            "status": "failed",
            "created_at": "2025-06-25T09:30:00Z"
        }
    ],
    "msg": "ok"
}
```

**前端轮询建议：**
- 上传后每 2 秒轮询一次，直到所有文档 `status` 不再是 `processing`
- `ready` 显示绿色状态，`processing` 显示黄色加载动画，`failed` 显示红色

---

### 4.3 删除文档

**`DELETE /api/knowledge/documents/{doc_id}`**

删除指定文档及其在 ChromaDB 中的所有向量分块。

**路径参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| doc_id | number | 文档 ID |

**响应：`204 No Content`**（无响应体）

**错误：文档不存在**

```json
{
    "code": 404,
    "data": null,
    "msg": "文档不存在"
}
```

---

## 五、统计接口

### 5.1 统计总览

**`GET /api/stats/overview`**

**响应：`200 OK`**

```json
{
    "code": 0,
    "data": {
        "total_sessions": 42,
        "total_messages": 356,
        "total_docs": 15,
        "kb_hit_rate": 78.5
    },
    "msg": "ok"
}
```

| 字段 | 说明 |
|------|------|
| total_sessions | 总会话数 |
| total_messages | 总消息数（user + assistant 各算一条） |
| total_docs | 知识库文档数（status=ready 的） |
| kb_hit_rate | 知识库命中率，百分比（qa_logs 中 kb_hit=1 的比例 × 100） |

---

### 5.2 热门问题

**`GET /api/stats/top-questions`**

获取最常被问到的问题 Top N。

**查询参数：**

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| limit | number | 否 | 10 | 返回数量上限 |
| days | number | 否 | 7 | 统计最近多少天的数据 |

**示例：`GET /api/stats/top-questions?limit=10&days=7`**

**响应：`200 OK`**

```json
{
    "code": 0,
    "data": [
        {
            "question": "黄鹤楼硬蓝的焦油量是多少",
            "count": 12
        },
        {
            "question": "烟草专卖许可证怎么办理",
            "count": 8
        },
        {
            "question": "卷烟分为哪几类",
            "count": 5
        }
    ],
    "msg": "ok"
}
```

**聚类逻辑说明：**
- 取最近 `days` 天的 qa_logs 中的 user_question
- 对相似问题做归并（精确匹配或简单去重）
- 按出现次数降序排列，返回前 `limit` 条

---

## 六、前端对接指南

### 6.1 SSE 接收示例（JavaScript）

```javascript
const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message: userInput })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';

while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // 保留未完成的行

    for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = JSON.parse(line.slice(6));

        switch (data.type) {
            case 'references':
                renderReferences(data.sources);  // 立即渲染引用卡片
                break;
            case 'reasoning':
                appendReasoning(data.text);       // 追加推理内容
                break;
            case 'content':
                appendContent(data.text);          // 追加回答内容
                break;
            case 'done':
                finishResponse();                  // 结束 loading
                break;
            case 'error':
                showError(data.text);              // 显示错误
                break;
        }
    }
}
```

### 6.2 前端状态管理

```typescript
// 会话列表
const sessions: Session[] = [];

// 当前会话消息
const messages: Message[] = [];

// 当前正在生成的回复（SSE 接收中）
const streamingResponse = {
    reasoning: '',        // 推理过程（累积）
    content: '',          // 回答内容（累积）
    sources: [],          // 引用来源
    isStreaming: false    // 是否正在接收
};
```

### 6.3 引用来源渲染逻辑

```
收到 references 事件：
  → 在回复区域上方/下方渲染引用来源卡片
  → 卡片显示：编号、标题、文件名
  → 点击卡片展开 content（命中的原文片段）

收到 content 事件：
  → 在引用来源卡片下方逐字展示 AI 回复
```

### 6.4 错误处理

| 场景 | 前端处理 |
|------|---------|
| SSE 连接失败 | 提示"网络连接失败，请重试"，保留用户输入 |
| SSE 内 error 事件 | 显示错误信息，保留用户输入 |
| 接口返回 400 | 显示 msg 字段的错误描述 |
| 接口返回 500 | 显示"服务器错误，请稍后重试" |
| 上传文件格式不支持 | 前端校验拦截，提示支持的格式列表 |
| 上传文件过大 | 前端校验拦截（建议单文件 ≤ 50MB） |
