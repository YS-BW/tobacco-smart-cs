"""RAG 检索服务：向量粗筛 + Reranker 精排。"""

from __future__ import annotations

from dataclasses import dataclass

import chromadb

from app.config import (
    CHROMA_PERSIST_DIR, CHROMA_COLLECTION,
    RAG_RETRIEVAL_TOP_K, RAG_RERANK_TOP_K, RAG_RERANK_THRESHOLD,
)
from app.services import embedding_service, rerank_service

_chroma_collection = None


def _get_collection():
    """获取 ChromaDB collection。"""
    global _chroma_collection
    if _chroma_collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
        _chroma_collection = client.get_or_create_collection(CHROMA_COLLECTION)
    return _chroma_collection


@dataclass
class RetrievalResult:
    """检索结果。"""
    content: str            # 子块内容
    parent_content: str     # 父块完整内容
    rerank_score: float     # 精排分数
    metadata: dict          # 元数据


def retrieve(query: str, top_k: int = RAG_RETRIEVAL_TOP_K, rerank_k: int = RAG_RERANK_TOP_K) -> list[RetrievalResult]:
    """检索 + 精排，返回 top-k 结果。"""
    collection = _get_collection()

    # 如果 collection 为空，直接返回
    if collection.count() == 0:
        return []

    # 第一轮：DashScope Embedding 向量粗筛
    query_vec = embedding_service.encode_query(query)

    results = collection.query(
        query_embeddings=[query_vec],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    documents = results["documents"][0]
    metadatas = results["metadatas"][0]

    if not documents:
        return []

    # 第二轮：DashScope Reranker 精排
    indexed = rerank_service.rerank(query, documents, rerank_k)

    retrieval_results = []
    for idx, score in indexed:
        # 低于阈值的跳过
        if score < RAG_RERANK_THRESHOLD:
            continue
        meta = metadatas[idx]
        retrieval_results.append(RetrievalResult(
            content=documents[idx],
            parent_content=meta.get("parent_content", documents[idx]),
            rerank_score=round(score, 4),
            metadata=meta,
        ))

    return retrieval_results


def warmup(query: str = "测试查询") -> None:
    """启动时预热 ChromaDB、DashScope Embedding 和 DashScope Reranker。"""
    collection = _get_collection()
    collection.count()
    embedding_service.warmup(query)
    rerank_service.warmup(query)
