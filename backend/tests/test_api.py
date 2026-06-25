"""API 接口测试。"""

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.db import database
from app.db.database import get_db, init_db


@pytest_asyncio.fixture(autouse=True)
async def setup_db(monkeypatch, tmp_path):
    """每个测试使用独立临时数据库，避免污染开发库。"""
    monkeypatch.setattr(database, "SQLITE_DB_PATH", str(tmp_path / "chat.db"))
    await init_db()
    yield
    db = await get_db()
    try:
        await db.execute("DELETE FROM qa_logs")
        await db.execute("DELETE FROM session_compressions")
        await db.execute("DELETE FROM messages")
        await db.execute("DELETE FROM sessions")
        await db.execute("DELETE FROM knowledge_docs")
        await db.commit()
    finally:
        await db.close()


@pytest_asyncio.fixture
async def client():
    """异步 HTTP 测试客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── 会话 CRUD ──

async def test_create_session(client: AsyncClient):
    """创建会话。"""
    resp = await client.post("/api/sessions", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert data["code"] == 0
    assert data["data"]["title"] == "新对话"
    assert data["data"]["message_count"] == 0


async def test_create_session_with_title(client: AsyncClient):
    """创建会话（自定义标题）。"""
    resp = await client.post("/api/sessions", json={"title": "测试会话"})
    assert resp.status_code == 201
    assert resp.json()["data"]["title"] == "测试会话"


async def test_list_sessions(client: AsyncClient):
    """获取会话列表。"""
    await client.post("/api/sessions", json={"title": "会话A"})
    await client.post("/api/sessions", json={"title": "会话B"})

    resp = await client.get("/api/sessions")
    assert resp.status_code == 200
    sessions = resp.json()["data"]
    assert len(sessions) == 2
    assert sessions[0]["title"] == "会话B"


async def test_get_messages_empty(client: AsyncClient):
    """获取空会话的消息历史。"""
    resp = await client.post("/api/sessions", json={})
    sid = resp.json()["data"]["id"]

    resp = await client.get(f"/api/sessions/{sid}/messages")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_get_messages_not_found(client: AsyncClient):
    """会话不存在返回 404。"""
    resp = await client.get("/api/sessions/nonexistent/messages")
    assert resp.status_code == 404


async def test_delete_session(client: AsyncClient):
    """删除会话。"""
    resp = await client.post("/api/sessions", json={})
    sid = resp.json()["data"]["id"]

    resp = await client.delete(f"/api/sessions/{sid}")
    assert resp.status_code == 204

    resp = await client.get("/api/sessions")
    assert len(resp.json()["data"]) == 0


async def test_delete_session_not_found(client: AsyncClient):
    """删除不存在的会话返回 404。"""
    resp = await client.delete("/api/sessions/nonexistent")
    assert resp.status_code == 404


# ── 对话接口 ──

async def test_chat_session_not_found(client: AsyncClient):
    """向不存在的会话发送消息返回 404。"""
    resp = await client.post("/api/chat", json={"session_id": "nonexistent", "message": "你好"})
    assert resp.status_code == 404


async def test_chat_sse_format(client: AsyncClient):
    """测试 SSE 流式响应格式（需要 LLM 服务可用）。"""
    resp = await client.post("/api/sessions", json={})
    sid = resp.json()["data"]["id"]

    resp = await client.post("/api/chat", json={"session_id": sid, "message": "你好"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = []
    for line in resp.text.split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            events.append(data["type"])

    assert "references" in events
    assert "done" in events


# ── 知识库接口 ──

async def test_list_documents_empty(client: AsyncClient):
    """获取空知识库文档列表。"""
    resp = await client.get("/api/knowledge/documents")
    assert resp.status_code == 200
    assert resp.json()["data"] == []


async def test_delete_document_not_found(client: AsyncClient):
    """删除不存在的文档返回 404。"""
    resp = await client.delete("/api/knowledge/documents/999")
    assert resp.status_code == 404


# ── 统计接口 ──

async def test_stats_overview(client: AsyncClient):
    """统计总览。"""
    resp = await client.get("/api/stats/overview")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "total_sessions" in data
    assert "total_messages" in data
    assert "total_docs" in data
    assert "kb_hit_rate" in data


async def test_top_questions(client: AsyncClient):
    """热门问题。"""
    resp = await client.get("/api/stats/top-questions")
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


async def test_top_questions_with_params(client: AsyncClient):
    """热门问题（带参数）。"""
    resp = await client.get("/api/stats/top-questions?limit=5&days=3")
    assert resp.status_code == 200
