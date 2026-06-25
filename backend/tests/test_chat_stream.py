"""对话流式服务的时序测试。"""

from collections.abc import AsyncGenerator
import asyncio
import time

import pytest

from app.db.database import get_db, init_db
from app.db import database
from app.services import chat_service
from app.utils.helpers import gen_uuid, now_iso


@pytest.fixture(autouse=True)
async def clean_db(monkeypatch, tmp_path):
    """每个测试使用独立临时数据库，避免污染开发库。"""
    monkeypatch.setattr(database, "SQLITE_DB_PATH", str(tmp_path / "chat.db"))
    await init_db()
    db = await get_db()
    try:
        await db.execute("DELETE FROM qa_logs")
        await db.execute("DELETE FROM session_compressions")
        await db.execute("DELETE FROM messages")
        await db.execute("DELETE FROM sessions")
        await db.commit()
    finally:
        await db.close()
    yield
    db = await get_db()
    try:
        await db.execute("DELETE FROM qa_logs")
        await db.execute("DELETE FROM session_compressions")
        await db.execute("DELETE FROM messages")
        await db.execute("DELETE FROM sessions")
        await db.commit()
    finally:
        await db.close()


async def _create_session() -> str:
    session_id = gen_uuid()
    ts = now_iso()
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO sessions (id, title, message_count, created_at, updated_at) VALUES (?, '新对话', 0, ?, ?)",
            (session_id, ts, ts),
        )
        await db.commit()
    finally:
        await db.close()
    return session_id


async def _insert_round(session_id: str, user: str, assistant: str) -> None:
    ts = now_iso()
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
            (session_id, user, ts),
        )
        await db.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'assistant', ?, ?)",
            (session_id, assistant, ts),
        )
        await db.execute(
            "UPDATE sessions SET message_count = message_count + 1, updated_at = ? WHERE id = ?",
            (ts, session_id),
        )
        await db.commit()
    finally:
        await db.close()


async def _fake_llm_stream(messages: list[dict]) -> AsyncGenerator[dict, None]:
    yield {"type": "content", "text": "测试回复"}
    yield {"type": "done", "text": ""}


async def test_done_is_sent_after_messages_are_persisted(monkeypatch):
    """前端收到 done 后立刻刷新历史，也应读到本轮问答。"""
    monkeypatch.setattr(chat_service.rag_service, "retrieve", lambda query: [])
    monkeypatch.setattr(chat_service.llm_service, "chat_completion_stream", _fake_llm_stream)

    session_id = await _create_session()

    async for chunk in chat_service.chat_stream(session_id, "测试问题"):
        if chunk.type == "done":
            break

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    assert [(row["role"], row["content"]) for row in rows] == [
        ("user", "测试问题"),
        ("assistant", "测试回复"),
    ]


async def test_slow_rag_retrieval_does_not_block_event_loop(monkeypatch):
    """RAG 检索较慢时，不能把整个 async 服务堵住。"""
    def slow_retrieve(query: str):
        time.sleep(0.2)
        return []

    monkeypatch.setattr(chat_service.rag_service, "retrieve", slow_retrieve)
    monkeypatch.setattr(chat_service.llm_service, "chat_completion_stream", _fake_llm_stream)

    session_id = await _create_session()
    events: list[str] = []

    async def ticker():
        await asyncio.sleep(0.01)
        events.append("ticker")

    async def read_first_chunk():
        stream = chat_service.chat_stream(session_id, "测试问题")
        await stream.__anext__()
        events.append("chunk")

    await asyncio.gather(read_first_chunk(), ticker())

    assert events[0] == "ticker"


async def test_follow_up_question_uses_previous_user_question_for_retrieval(monkeypatch):
    """短句追问应结合上一轮用户问题检索知识库。"""
    seen_queries: list[str] = []

    def capture_retrieve(query: str):
        seen_queries.append(query)
        return []

    monkeypatch.setattr(chat_service.rag_service, "retrieve", capture_retrieve)
    monkeypatch.setattr(chat_service.llm_service, "chat_completion_stream", _fake_llm_stream)

    session_id = await _create_session()
    await _insert_round(session_id, "黄鹤楼硬红的焦油量是多少？", "黄鹤楼硬红的焦油量为11mg/支。")

    async for chunk in chat_service.chat_stream(session_id, "那软蓝呢？"):
        if chunk.type == "done":
            break

    assert seen_queries == ["黄鹤楼硬红的焦油量是多少？\n那软蓝呢？"]


async def test_intent_classifier_can_skip_rag_for_chitchat(monkeypatch):
    """意图识别判定不需要知识库时，不应调用 RAG，也不应展示引用。"""
    retrieve_called = False
    llm_messages: list[list[dict]] = []

    async def no_rag(*, user_message: str, retrieval_query: str) -> bool:
        return False

    def retrieve(query: str):
        nonlocal retrieve_called
        retrieve_called = True
        return []

    async def capture_llm_stream(messages: list[dict]) -> AsyncGenerator[dict, None]:
        llm_messages.append(messages)
        yield {"type": "content", "text": "测试回复"}
        yield {"type": "done", "text": ""}

    monkeypatch.setattr(chat_service.intent_service, "should_use_rag", no_rag)
    monkeypatch.setattr(chat_service.rag_service, "retrieve", retrieve)
    monkeypatch.setattr(chat_service.llm_service, "chat_completion_stream", capture_llm_stream)

    session_id = await _create_session()
    chunks = []
    async for chunk in chat_service.chat_stream(session_id, "你好"):
        chunks.append(chunk)
        if chunk.type == "done":
            break

    references = next(chunk for chunk in chunks if chunk.type == "references")
    assert references.sources == []
    assert retrieve_called is False
    assert "未检索到相关知识库内容" not in llm_messages[0][0]["content"]


async def test_intent_classifier_uses_retrieval_query_for_follow_up(monkeypatch):
    """短句追问做意图识别时，应看到结合上一轮问题后的 query。"""
    seen: list[tuple[str, str]] = []

    async def capture_intent(*, user_message: str, retrieval_query: str) -> bool:
        seen.append((user_message, retrieval_query))
        return True

    monkeypatch.setattr(chat_service.intent_service, "should_use_rag", capture_intent)
    monkeypatch.setattr(chat_service.rag_service, "retrieve", lambda query: [])
    monkeypatch.setattr(chat_service.llm_service, "chat_completion_stream", _fake_llm_stream)

    session_id = await _create_session()
    await _insert_round(session_id, "黄鹤楼硬红的焦油量是多少？", "黄鹤楼硬红的焦油量为11mg/支。")

    async for chunk in chat_service.chat_stream(session_id, "那软蓝呢？"):
        if chunk.type == "done":
            break

    assert seen == [("那软蓝呢？", "黄鹤楼硬红的焦油量是多少？\n那软蓝呢？")]
