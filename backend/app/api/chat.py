"""对话 + 会话 CRUD 接口。"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.db.database import get_db
from app.models.schemas import ApiResponse, ChatRequest, MessageInfo, SessionCreate, SessionInfo, SourceInfo
from app.services.chat_service import chat_stream
from app.utils.helpers import gen_uuid, now_iso

router = APIRouter()


# ── 对话接口 ──

@router.post("/chat")
async def post_chat(req: ChatRequest):
    """发送消息，返回 SSE 流式响应。session_id 为空时自动创建会话。"""
    session_id = req.session_id
    ts = now_iso()

    db = await get_db()
    try:
        if session_id:
            cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
            row = await cursor.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="会话不存在")
        else:
            # 自动创建会话
            session_id = gen_uuid()
            await db.execute(
                "INSERT INTO sessions (id, title, message_count, created_at, updated_at) VALUES (?, ?, 0, ?, ?)",
                (session_id, "新对话", ts, ts),
            )
            await db.commit()
    finally:
        await db.close()

    async def event_generator():
        # 首帧推送 session_id，方便前端获取自动创建的会话 ID
        yield f'data: {{"type":"session","session_id":"{session_id}"}}\n\n'
        async for chunk in chat_stream(session_id, req.message):
            yield f"data: {chunk.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 会话 CRUD ──

@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreate | None = None):
    """创建新会话。"""
    session_id = gen_uuid()
    title = body.title if body and body.title else "新对话"
    ts = now_iso()

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO sessions (id, title, message_count, created_at, updated_at) VALUES (?, ?, 0, ?, ?)",
            (session_id, title, ts, ts),
        )
        await db.commit()
    finally:
        await db.close()

    return ApiResponse(data=SessionInfo(
        id=session_id, title=title, message_count=0, created_at=ts, updated_at=ts,
    ))


@router.get("/sessions")
async def list_sessions():
    """获取会话列表，按 updated_at 降序。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, title, message_count, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
        )
        rows = await cursor.fetchall()
        sessions = [
            SessionInfo(
                id=r["id"], title=r["title"], message_count=r["message_count"],
                created_at=r["created_at"], updated_at=r["updated_at"],
            )
            for r in rows
        ]
        return ApiResponse(data=sessions)
    finally:
        await db.close()


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """获取指定会话的消息历史。"""
    db = await get_db()
    try:
        # 验证会话存在
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if (await cursor.fetchone()) is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        cursor = await db.execute(
            "SELECT id, role, content, reasoning_content, `references`, created_at "
            "FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        rows = await cursor.fetchall()
        messages = []
        for r in rows:
            refs = None
            if r["references"]:
                refs = [SourceInfo(**s) for s in json.loads(r["references"])]
            messages.append(MessageInfo(
                id=r["id"], role=r["role"], content=r["content"],
                reasoning_content=r["reasoning_content"], references=refs,
                created_at=r["created_at"],
            ))
        return ApiResponse(data=messages)
    finally:
        await db.close()


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str):
    """删除会话及其所有关联数据。"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id FROM sessions WHERE id = ?", (session_id,))
        if (await cursor.fetchone()) is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        await db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await db.commit()
    finally:
        await db.close()
