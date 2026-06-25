"""DashScope rerank service."""

from __future__ import annotations

import httpx

from app.config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_RERANK_BASE_URL,
    DASHSCOPE_RERANK_INSTRUCT,
    DASHSCOPE_RERANK_MODEL,
    DASHSCOPE_TIMEOUT,
)

_http_client = None


def _get_http_client():
    """Lazy-load a sync HTTP client for RAG calls running in a worker thread."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=DASHSCOPE_TIMEOUT)
    return _http_client


def rerank(query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
    """Return ``(document_index, relevance_score)`` pairs ordered by relevance."""
    if not documents or top_n <= 0:
        return []
    return _dashscope_rerank(query, documents, top_n)


def warmup(query: str = "测试查询") -> None:
    """Warm up the configured reranker provider."""
    rerank(query, [query], 1)


def _dashscope_rerank(query: str, documents: list[str], top_n: int) -> list[tuple[int, float]]:
    """Call DashScope's OpenAI-compatible rerank API."""
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("DASHSCOPE_API_KEY is required for RAG rerank")

    payload = {
        "model": DASHSCOPE_RERANK_MODEL,
        "query": query,
        "documents": documents,
        "top_n": top_n,
    }
    if DASHSCOPE_RERANK_INSTRUCT:
        payload["instruct"] = DASHSCOPE_RERANK_INSTRUCT

    response = _get_http_client().post(
        f"{DASHSCOPE_RERANK_BASE_URL.rstrip('/')}/reranks",
        headers={
            "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
    )
    response.raise_for_status()
    body = response.json()
    results = body.get("results") or body.get("output", {}).get("results", [])
    return [
        (int(item["index"]), float(item.get("relevance_score", item.get("score", 0.0))))
        for item in results
    ]
