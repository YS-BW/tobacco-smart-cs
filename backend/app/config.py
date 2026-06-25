"""项目配置项，从环境变量读取。"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent

# LLM
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "mimo-v2.5")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))

# DashScope RAG APIs
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_TIMEOUT = float(os.getenv("DASHSCOPE_TIMEOUT", "30"))
DASHSCOPE_EMBEDDING_BASE_URL = os.getenv(
    "DASHSCOPE_EMBEDDING_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1",
)
DASHSCOPE_EMBEDDING_MODEL = os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")
DASHSCOPE_EMBEDDING_DIMENSIONS = int(os.getenv("DASHSCOPE_EMBEDDING_DIMENSIONS", "1024"))
DASHSCOPE_EMBEDDING_BATCH_SIZE = min(int(os.getenv("DASHSCOPE_EMBEDDING_BATCH_SIZE", "10")), 10)
DASHSCOPE_RERANK_BASE_URL = os.getenv(
    "DASHSCOPE_RERANK_BASE_URL",
    "https://dashscope.aliyuncs.com/compatible-api/v1",
)
DASHSCOPE_RERANK_MODEL = os.getenv("DASHSCOPE_RERANK_MODEL", "qwen3-rerank")
DASHSCOPE_RERANK_INSTRUCT = os.getenv(
    "DASHSCOPE_RERANK_INSTRUCT",
    "Given a web search query, retrieve relevant passages that answer the query.",
)

# ChromaDB
CHROMA_PERSIST_DIR = str(BASE_DIR / "data" / "chroma")
CHROMA_COLLECTION = "knowledge_base"

# RAG
RAG_RETRIEVAL_TOP_K = int(os.getenv("RAG_RETRIEVAL_TOP_K", "6"))
RAG_RERANK_TOP_K = int(os.getenv("RAG_RERANK_TOP_K", "3"))
RAG_RERANK_THRESHOLD = float(os.getenv("RAG_RERANK_THRESHOLD", "0.3"))
RAG_WARMUP_QUERY = os.getenv("RAG_WARMUP_QUERY", "黄鹤楼硬红的焦油量是多少？")
MODEL_WARMUP_ENABLED = os.getenv("MODEL_WARMUP_ENABLED", "true").lower() == "true"

# 分块
CHUNK_MAX_SIZE = int(os.getenv("CHUNK_MAX_SIZE", "1000"))
CHUNK_TARGET_SIZE = int(os.getenv("CHUNK_TARGET_SIZE", "500"))

# 上下文压缩
COMPRESSION_ROUND_INTERVAL = int(os.getenv("COMPRESSION_ROUND_INTERVAL", "15"))
COMPRESSION_MAX_TOPIC_LENGTH = int(os.getenv("COMPRESSION_MAX_TOPIC_LENGTH", "50"))

# MinerU
MINERU_TOKEN = os.getenv("MINERU_TOKEN", "")
MINERU_SCRIPT = str(Path.home() / ".agents/skills/mineru/scripts/mineru.py")

# 文件存储
RAW_DIR = str(BASE_DIR / "data" / "raw")
PROCESSED_DIR = str(BASE_DIR / "data" / "processed")

# 数据库
SQLITE_DB_PATH = str(BASE_DIR / "data" / "chat.db")
