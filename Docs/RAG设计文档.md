# RAG 设计文档

## 一、整体流程

```
原始文档 (PDF/Word/图片/Markdown)
        │
        ▼
   上传至系统
        │
        ▼
   MinerU 解析 → Markdown
        │
        ▼
   结构化分块（按标题层级）
        │
        ▼
   bge-large-zh-v1.5 向量化
        │
        ▼
   ChromaDB 存储
        │
        ════════════════════ 知识库构建完成 ════════════════════
        │
用户提问 ──→ bge-large-zh-v1.5 向量检索 Top-20（粗筛）
        │
        ▼
   bge-reranker-v2-m3 精排 → Top-5
        │
        ▼
   拼入 Prompt → Mimo-v2.5 生成回答
```

## 二、文档解析（MinerU）

### 输入格式

| 格式 | 扩展名 | 处理方式 |
|------|--------|---------|
| PDF | `.pdf` | MinerU Standard API |
| Word | `.doc` `.docx` | MinerU Standard API |
| 图片 | `.png` `.jpg` `.jpeg` `.webp` | MinerU Standard API + OCR |
| Markdown | `.md` | 直接使用，跳过 MinerU |

### MinerU 输出结构示例

```markdown
# 文档标题                    ← H1（文章主题）

开头摘要段落...

## 第一大节                   ← H2（完整章节）
### 子节 1                    ← H3（语义段落）
具体内容...
### 子节 2                    ← H3
具体内容...
#### 更细的子节                ← H4
具体内容...

## 第二大节                   ← H2
...
```

**特征：**
- 标题层级清晰（H1 → H2 → H3 → H4）
- 段落边界明确，句子不会被截断
- 表格保留完整结构（`<table>` 标签）
- 图片保留链接，参考文献保留标注

## 三、分块策略（结构化分块 + 父子分块）

### 设计思路

利用 MinerU 输出的 Markdown 标题结构进行语义分块，而非按字符硬切。

### 分块规则

```
检索用子块（Child Chunk）：按 ###（H3）级别切分
    │
    └── 每个 H3 section = 1 个子块
        用于向量检索，粒度细，匹配精准

给 LLM 的父块（Parent Chunk）：按 ##（H2）级别切分
    │
    └── 每个 H2 section = 1 个父块
        命中子块后返回其所属父块，上下文完整
```

### 父子关系示例

```
## 烟草加工                    ← 父块（给 LLM 的完整上下文）
├── ### 风干                   ← 子块 1（用于检索）
├── ### 烤干                   ← 子块 2（用于检索）
├── ### 热风管干燥             ← 子块 3（用于检索）
└── ### 日晒干燥法             ← 子块 4（用于检索）
```

检索时匹配到"风干"子块 → 返回整个"烟草加工"父块给 LLM，LLM 拿到完整的四种加工方法上下文。

### 二次切分

如果单个 H3 块超过 1000 字，按段落（`\n\n`）二次切分，每块保持在 500-800 字。

### 分块数据结构

```python
@dataclass
class Chunk:
    chunk_id: str           # 格式: "doc_{doc_id}_chunk_{index}"
    content: str            # 块的文本内容
    parent_content: str     # 所属父块的完整内容
    metadata: dict          # {source, doc_id, heading_path, chunk_index}

# 示例
Chunk(
    chunk_id="doc_1_chunk_3",
    content="风干（Air-Cured）：在通风良好的棚中放在架子上自然风干6至8周...",
    parent_content="## 烟草加工\n\n烟叶收获后，需要干燥醇化。常用方法有四种：\n\n### 风干\n...",
    metadata={
        "source": "烟草百科.pdf",
        "doc_id": 1,
        "heading_path": "# 烟草 > ## 烟草加工 > ### 风干",
        "chunk_index": 3
    }
)
```

## 四、向量化（Embedding）

### 模型

- **模型**：`BAAI/bge-large-zh-v1.5`
- **维度**：1024
- **加载方式**：`sentence-transformers` 本地加载
- **设备**：CPU（可配置为 GPU）

### 编码方式

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-large-zh-v1.5")

# bge 模型需要加 query 前缀用于检索
query_embedding = model.encode("query: 黄鹤楼硬蓝的焦油量是多少")
doc_embedding = model.encode("风干（Air-Cured）：在通风良好的棚中...")
```

## 五、向量存储（ChromaDB）

### Collection 结构

```
Collection: "knowledge_base"
├── ids:        ["doc_1_chunk_0", "doc_1_chunk_1", ...]
├── documents:  ["子块文本内容", ...]
├── embeddings: [[0.12, -0.34, ...], ...]              # 1024 维
└── metadatas:  [
      {
        "source": "烟草百科.pdf",
        "doc_id": 1,
        "heading_path": "# 烟草 > ## 烟草加工 > ### 风干",
        "chunk_index": 0,
        "parent_content": "## 烟草加工\n\n完整父块内容..."
      },
      ...
    ]
```

**关键：`parent_content` 存在 metadata 中**，检索命中子块时直接从 metadata 取出父块，无需二次查询。

### 持久化

ChromaDB 数据持久化到 `data/chroma/` 目录，重启后自动加载。

## 六、检索与精排

### 第一轮：向量粗筛

```python
# 用户问题向量化
query_vec = embedding_model.encode("query: " + user_question)

# ChromaDB 检索 Top-20
results = collection.query(
    query_embeddings=[query_vec],
    n_results=20,
    include=["documents", "metadatas", "distances"]
)
```

### 第二轮：Reranker 精排

```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder("BAAI/bge-reranker-v2-m3")

# 构造 (query, doc) 对
pairs = [(user_question, doc) for doc in results["documents"][0]]

# 计算精排分数
scores = reranker.predict(pairs)

# 按分数降序，取 Top-5
top5_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:5]
```

### 最终输出

```python
# 返回给 chat_service 的结果
[
    {
        "content": "子块文本（用于展示匹配到的内容）",
        "parent_content": "父块完整文本（拼入 prompt 给 LLM）",
        "rerank_score": 0.89,
        "metadata": {...}
    },
    ...
]
```

## 七、Prompt 组装

### 整体结构

```
messages = [
    {
        "role": "system",
        "content": "[角色设定]\n...\n\n[知识库检索结果]\n...\n\n[上下文摘要]\n..."
    },
    {"role": "user", "content": "第一轮问题"},
    {"role": "assistant", "content": "第一轮回答"},
    {"role": "user", "content": "第二轮问题"},
    {"role": "assistant", "content": "第二轮回答"},
    ...
    {"role": "user", "content": "当前问题"}
]
```

**一个 system message，内部按区块组织。对话历史用标准 user/assistant 交替。**

### System Message 内容

```
[角色设定]
你是烟草行业智能客服助手。请基于提供的知识库内容回答用户问题。

规则：
1. 优先使用知识库中的信息回答
2. 如果知识库中没有相关信息，请如实告知并尽量给出一般性建议
3. 回答要简洁、专业、准确
4. 不要编造不存在的数据或信息

[知识库检索结果]

文档1（精排分数：0.89）：
{parent_content_1}

文档2（精排分数：0.85）：
{parent_content_2}

文档3（精排分数：0.82）：
{parent_content_3}

（如果无检索结果则显示：未检索到相关知识库内容）

[上下文摘要]（如有，多组摘要按时间顺序排列）
第1-15轮摘要：
1. 用户询问了焦油量标准
2. 用户了解了许可证办理流程
...

第16-30轮摘要：
1. 用户询问了卷烟分类
...
```

### RAG 检索无结果时

当 Reranker 最高分数 < 0.3 时，知识库区块替换为：

```
[知识库检索结果]
未检索到相关知识库内容。请根据你的通用知识回答，
并在回答开头说明"以下为通用参考信息，具体请以官方资料为准"。
```

### 组装代码逻辑

```python
def build_messages(session_id: str, user_message: str, rag_results: list) -> list[dict]:
    # 1. 构建 system message
    system_parts = [ROLE_PROMPT]

    # RAG 知识库内容
    if rag_results:
        kb_section = format_rag_results(rag_results)  # 文档1: ...\n文档2: ...
    else:
        kb_section = "未检索到相关知识库内容..."
    system_parts.append(f"[知识库检索结果]\n{kb_section}")

    # 上下文压缩摘要
    compressions = get_compressions(session_id)  # 查询 status=done 的摘要
    if compressions:
        summary_section = format_compressions(compressions)
        system_parts.append(f"[上下文摘要]\n{summary_section}")

    system_message = {"role": "system", "content": "\n\n".join(system_parts)}

    # 2. 获取对话历史
    history = get_recent_messages(session_id, limit=15)
    history_messages = [{"role": m.role, "content": m.content} for m in history]

    # 3. 组装
    return [system_message] + history_messages + [{"role": "user", "content": user_message}]
```

## 八、技术选型汇总

| 组件 | 模型/工具 | 用途 | 运行方式 |
|------|----------|------|---------|
| 文档解析 | MinerU Standard API | PDF/Word/图片 → Markdown | 云端 API（需 Token） |
| 分块 | 自定义结构化分块 | 按 Markdown 标题层级切分 | 本地 |
| Embedding | BAAI/bge-large-zh-v1.5 | 文本向量化 | 本地（sentence-transformers） |
| 向量数据库 | ChromaDB | 向量存储与检索 | 本地 |
| Reranker | BAAI/bge-reranker-v2-m3 | 粗排结果精排 | 本地（sentence-transformers） |
| LLM | Mimo-v2.5 | 最终回答生成 | 云端 API |

## 九、配置项

```python
# Embedding
EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"
EMBEDDING_DEVICE = "cpu"

# Reranker
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
RERANKER_DEVICE = "cpu"

# ChromaDB
CHROMA_PERSIST_DIR = "./data/chroma"
CHROMA_COLLECTION = "knowledge_base"

# RAG
RAG_RETRIEVAL_TOP_K = 20        # 向量粗筛数量
RAG_RERANK_TOP_K = 5            # Reranker 精排后保留数量
RAG_RERANK_THRESHOLD = 0.3      # 低于此值视为未命中

# 分块
CHUNK_MAX_SIZE = 1000           # 单块最大字数，超过则二次切分
CHUNK_TARGET_SIZE = 500         # 二次切分目标字数

# MinerU
MINERU_TOKEN = "..."
```
