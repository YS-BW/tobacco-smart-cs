"""DashScope RAG provider tests."""

from app.services import embedding_service, rerank_service


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeHttpClient:
    def __init__(self, responses: list[dict]):
        self.responses = responses
        self.requests: list[tuple[str, dict, dict]] = []

    def post(self, url: str, headers: dict, json: dict) -> FakeResponse:
        self.requests.append((url, headers, json))
        return FakeResponse(self.responses.pop(0))


def test_dashscope_embedding_batches_requests_and_preserves_order(monkeypatch):
    """DashScope embedding should use OpenAI-compatible batches of at most 10 rows."""
    fake_client = FakeHttpClient([
        {
            "data": [
                {"index": 1, "embedding": [1.0]},
                {"index": 0, "embedding": [0.0]},
            ]
        },
        {
            "data": [
                {"index": 0, "embedding": [2.0]},
            ]
        },
    ])
    monkeypatch.setattr(embedding_service, "DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(embedding_service, "DASHSCOPE_EMBEDDING_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr(embedding_service, "DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4")
    monkeypatch.setattr(embedding_service, "DASHSCOPE_EMBEDDING_DIMENSIONS", 1024)
    monkeypatch.setattr(embedding_service, "DASHSCOPE_EMBEDDING_BATCH_SIZE", 2)
    monkeypatch.setattr(embedding_service, "_get_http_client", lambda: fake_client)

    embeddings = embedding_service.encode_documents(["a", "b", "c"])

    assert embeddings == [[0.0], [1.0], [2.0]]
    assert [req[2]["input"] for req in fake_client.requests] == [["a", "b"], ["c"]]
    assert fake_client.requests[0][0] == "https://example.test/v1/embeddings"
    assert fake_client.requests[0][2]["dimensions"] == 1024


def test_dashscope_reranker_parses_qwen3_results(monkeypatch):
    """DashScope qwen3-rerank returns top-level results ordered by relevance."""
    fake_client = FakeHttpClient([
        {
            "results": [
                {"index": 2, "relevance_score": 0.91},
                {"index": 0, "relevance_score": 0.32},
            ]
        }
    ])
    monkeypatch.setattr(rerank_service, "DASHSCOPE_API_KEY", "test-key")
    monkeypatch.setattr(rerank_service, "DASHSCOPE_RERANK_BASE_URL", "https://example.test/rerank")
    monkeypatch.setattr(rerank_service, "DASHSCOPE_RERANK_MODEL", "qwen3-rerank")
    monkeypatch.setattr(rerank_service, "DASHSCOPE_RERANK_INSTRUCT", "Retrieve answers.")
    monkeypatch.setattr(rerank_service, "_get_http_client", lambda: fake_client)

    ranked = rerank_service.rerank("问题", ["文档 A", "文档 B", "文档 C"], top_n=2)

    assert ranked == [(2, 0.91), (0, 0.32)]
    assert fake_client.requests[0][0] == "https://example.test/rerank/reranks"
    assert fake_client.requests[0][2] == {
        "model": "qwen3-rerank",
        "query": "问题",
        "documents": ["文档 A", "文档 B", "文档 C"],
        "top_n": 2,
        "instruct": "Retrieve answers.",
    }
