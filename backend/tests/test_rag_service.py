"""RAG 服务测试。"""

from app.services import rag_service


def test_warmup_loads_models_and_runs_minimal_inference(monkeypatch):
    """预热应加载向量库，并触发 DashScope Embedding 和 Reranker。"""
    calls: list[str] = []

    class FakeCollection:
        def count(self):
            calls.append("collection.count")
            return 0

    monkeypatch.setattr(rag_service, "_get_collection", lambda: FakeCollection())
    monkeypatch.setattr(rag_service.embedding_service, "warmup", lambda query: calls.append(f"embedding.warmup:{query}"))
    monkeypatch.setattr(rag_service.rerank_service, "warmup", lambda query: calls.append(f"rerank.warmup:{query}"))

    rag_service.warmup("测试查询")

    assert calls == [
        "collection.count",
        "embedding.warmup:测试查询",
        "rerank.warmup:测试查询",
    ]
