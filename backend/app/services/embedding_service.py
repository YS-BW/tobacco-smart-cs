"""DashScope embedding service."""

from __future__ import annotations

import httpx

from app.config import (
    DASHSCOPE_API_KEY,
    DASHSCOPE_EMBEDDING_BASE_URL,
    DASHSCOPE_EMBEDDING_BATCH_SIZE,
    DASHSCOPE_EMBEDDING_DIMENSIONS,
    DASHSCOPE_EMBEDDING_MODEL,
    DASHSCOPE_TIMEOUT,
)

_http_client = None


def _get_http_client():
    """Lazy-load a sync HTTP client for RAG calls running in a worker thread."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=DASHSCOPE_TIMEOUT)
    return _http_client


def encode_query(query: str) -> list[float]:
    """Encode a search query with DashScope."""
    return _dashscope_embed([query])[0]


def encode_documents(documents: list[str]) -> list[list[float]]:
    """Encode documents with DashScope."""
    if not documents:
        return []
    return _dashscope_embed(documents)


def warmup(query: str = "测试查询") -> None:
    """Warm up the configured embedding provider."""
    encode_query(query)


def _dashscope_embed(texts: list[str]) -> list[list[float]]:
    """Call DashScope's OpenAI-compatible embeddings API."""
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("DASHSCOPE_API_KEY is required for RAG embeddings")

    client = _get_http_client()
    embeddings: list[list[float]] = []
    batch_size = max(1, min(DASHSCOPE_EMBEDDING_BATCH_SIZE, 10))

    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        payload = {
            "model": DASHSCOPE_EMBEDDING_MODEL,
            "input": batch,
            "encoding_format": "float",
        }
        if DASHSCOPE_EMBEDDING_DIMENSIONS:
            payload["dimensions"] = DASHSCOPE_EMBEDDING_DIMENSIONS

        response = client.post(
            f"{DASHSCOPE_EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
            headers={
                "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()["data"]
        ordered = sorted(data, key=lambda item: item["index"])
        embeddings.extend(item["embedding"] for item in ordered)

    return embeddings
