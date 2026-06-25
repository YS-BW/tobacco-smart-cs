"""LLM intent detection tests."""

from app.services import intent_service


async def test_should_use_rag_parses_false_decision(monkeypatch):
    """主模型判定闲聊时，应跳过 RAG。"""
    seen_messages: list[list[dict]] = []

    async def fake_completion(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
        seen_messages.append(messages)
        return '{"use_rag": false, "reason": "greeting"}'

    monkeypatch.setattr(intent_service.llm_service, "chat_completion_text", fake_completion)

    assert await intent_service.should_use_rag(user_message="你好", retrieval_query="你好") is False
    assert "你好" in seen_messages[0][-1]["content"]


async def test_should_use_rag_falls_back_to_true_on_bad_model_output(monkeypatch):
    """意图识别输出不可解析时，保守地走 RAG。"""
    async def fake_completion(messages: list[dict], *, max_tokens: int, temperature: float) -> str:
        return "我觉得不用"

    monkeypatch.setattr(intent_service.llm_service, "chat_completion_text", fake_completion)

    assert await intent_service.should_use_rag(user_message="许可证怎么办", retrieval_query="许可证怎么办") is True
