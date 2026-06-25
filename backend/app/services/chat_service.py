"""对话编排服务：RAG 检索 → Prompt 组装 → LLM 流式生成 → 持久化。"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from app.config import COMPRESSION_ROUND_INTERVAL
from app.db.database import get_db
from app.models.schemas import ChatChunk, SourceInfo
from app.services import compression, intent_service, llm_service, rag_service
from app.utils.helpers import now_iso

logger = logging.getLogger(__name__)

# 角色设定 Prompt
ROLE_PROMPT = """你是烟草行业智能客服助手。请基于提供的知识库内容回答用户问题。

规则：
1. 优先使用知识库中的信息回答
2. 如果知识库中没有相关信息，请如实告知并尽量给出一般性建议
3. 回答要简洁、专业、准确
4. 不要编造不存在的数据或信息"""


def _format_rag_results(results: list[rag_service.RetrievalResult]) -> str:
    """将 RAG 检索结果格式化为 system message 片段。"""
    if not results:
        return '未检索到相关知识库内容。请根据你的通用知识回答，并在回答开头说明"以下为通用参考信息，具体请以官方资料为准"。'
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"文档{i}（精排分数：{r.rerank_score}）：\n{r.parent_content}")
    return "\n\n".join(parts)


def _format_compressions(comps: list[dict]) -> str:
    """将压缩摘要格式化为 system message 片段。"""
    parts = []
    for c in comps:
        topics = "、".join(c["topics"])
        parts.append(f"第{c['round_start']}-{c['round_end']}轮摘要：{topics}")
    return "\n".join(parts)


def _build_sources(results: list[rag_service.RetrievalResult]) -> list[SourceInfo]:
    """从 RAG 结果构建引用来源列表。"""
    sources = []
    for i, r in enumerate(results, 1):
        meta = r.metadata
        sources.append(SourceInfo(
            index=i,
            title=meta.get("source", ""),
            filename=meta.get("source", ""),
            content=r.content[:200],
        ))
    return sources


def _looks_like_follow_up(message: str) -> bool:
    """判断是否需要结合上一轮上下文做检索。"""
    text = message.strip()
    if len(text) <= 12:
        return True
    markers = ("那", "呢", "它", "这个", "那个", "同样", "还有", "继续", "再说", "也", "分别")
    return any(marker in text for marker in markers)


async def _build_retrieval_query(session_id: str, user_message: str) -> str:
    """为 RAG 组装更完整的检索 query。"""
    if not _looks_like_follow_up(user_message):
        return user_message

    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT content FROM messages "
            "WHERE session_id = ? AND role = 'user' "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
    finally:
        await db.close()

    if not row:
        return user_message

    previous_question = (row["content"] or "").strip()
    if not previous_question or previous_question == user_message.strip():
        return user_message
    return f"{previous_question}\n{user_message}"


async def _build_messages(
    session_id: str,
    user_message: str,
    rag_results: list[rag_service.RetrievalResult],
    *,
    use_rag: bool,
) -> list[dict]:
    """组装完整的 LLM messages 数组。"""
    # 1. System message
    parts = [ROLE_PROMPT]
    if use_rag:
        parts.append(f"[知识库检索结果]\n{_format_rag_results(rag_results)}")
    else:
        parts.append("[知识库状态]\n当前问题无需查询知识库，请直接自然回答，不要声称检索了资料。")

    # 压缩摘要
    comps = await compression.get_compressions(session_id)
    if comps:
        parts.append(f"[上下文摘要]\n{_format_compressions(comps)}")

    system_message = {"role": "system", "content": "\n\n".join(parts)}

    # 2. 对话历史（最近 15 轮 = 30 条消息）
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT role, content FROM messages "
            "WHERE session_id = ? ORDER BY id DESC LIMIT 30",
            (session_id,),
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    history = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]

    # 3. 组装
    return [system_message] + history + [{"role": "user", "content": user_message}]


async def chat_stream(session_id: str, user_message: str) -> AsyncGenerator[ChatChunk, None]:
    """对话主流程：RAG → references → LLM 流式 → done。"""

    # 1. 意图识别 + RAG 检索
    rag_query = await _build_retrieval_query(session_id, user_message)
    use_rag = await intent_service.should_use_rag(user_message=user_message, retrieval_query=rag_query)
    rag_results = await asyncio.to_thread(rag_service.retrieve, rag_query) if use_rag else []
    sources = _build_sources(rag_results)

    # 2. 推送 references 帧
    yield ChatChunk(type="references", sources=sources)

    # 3. 组装 messages
    messages = await _build_messages(session_id, user_message, rag_results, use_rag=use_rag)

    # 4. LLM 流式生成
    start_time = time.time()
    full_content = ""
    full_reasoning = ""

    try:
        async for chunk in llm_service.chat_completion_stream(messages):
            if chunk["type"] == "reasoning":
                full_reasoning += chunk["text"]
                yield ChatChunk(type="reasoning", text=chunk["text"])
            elif chunk["type"] == "content":
                full_content += chunk["text"]
                yield ChatChunk(type="content", text=chunk["text"])
            elif chunk["type"] == "done":
                break
    except Exception as e:
        logger.error("LLM 调用失败: %s", e)
        yield ChatChunk(type="error", text="模型调用失败，请重试")
        return

    elapsed_ms = int((time.time() - start_time) * 1000)

    # 5. 持久化完成后再推送 done，避免前端收到 done 后刷新历史时抢跑
    await _save_after_response(
        session_id=session_id,
        user_message=user_message,
        content=full_content,
        reasoning=full_reasoning,
        sources=sources,
        elapsed_ms=elapsed_ms,
        rag_results=rag_results,
    )

    # 6. 推送 done 帧
    yield ChatChunk(type="done")


async def _save_after_response(
    session_id: str,
    user_message: str,
    content: str,
    reasoning: str,
    sources: list[SourceInfo],
    elapsed_ms: int,
    rag_results: list[rag_service.RetrievalResult],
) -> None:
    """LLM 回复完成后：存消息、更新 session、记 qa_log、触发压缩。"""
    db = await get_db()
    try:
        now = now_iso()

        # 存 user 消息
        await db.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, 'user', ?, ?)",
            (session_id, user_message, now),
        )

        # 存 assistant 消息
        refs_json = json.dumps([s.model_dump() for s in sources], ensure_ascii=False) if sources else None
        await db.execute(
            "INSERT INTO messages (session_id, role, content, reasoning_content, `references`, created_at) "
            "VALUES (?, 'assistant', ?, ?, ?, ?)",
            (session_id, content, reasoning or None, refs_json, now),
        )

        # 更新 session
        cursor = await db.execute(
            "SELECT message_count FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            logger.warning("会话不存在: %s", session_id)
            await db.commit()
            return

        new_count = row["message_count"] + 1
        # 首条消息时更新标题
        if new_count == 1:
            title = user_message[:20]
            await db.execute(
                "UPDATE sessions SET title = ?, message_count = ?, updated_at = ? WHERE id = ?",
                (title, new_count, now, session_id),
            )
        else:
            await db.execute(
                "UPDATE sessions SET message_count = ?, updated_at = ? WHERE id = ?",
                (new_count, now, session_id),
            )

        # 记录 qa_log
        retrieved_ids = [r.metadata.get("doc_id") for r in rag_results if r.metadata.get("doc_id")]
        max_score = max((r.rerank_score for r in rag_results), default=0.0)
        kb_hit = 1 if rag_results else 0
        await db.execute(
            "INSERT INTO qa_logs (session_id, user_question, retrieved_doc_ids, max_similarity, kb_hit, response_time_ms) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, user_message, json.dumps(retrieved_ids), max_score, kb_hit, elapsed_ms),
        )

        await db.commit()

        # 触发压缩（异步）
        if new_count > 0 and new_count % COMPRESSION_ROUND_INTERVAL == 0:
            round_start = new_count - COMPRESSION_ROUND_INTERVAL + 1
            round_end = new_count
            asyncio.create_task(compression.compress_session(session_id, round_start, round_end))
            logger.info("触发异步压缩: session=%s rounds=%d-%d", session_id, round_start, round_end)

    except Exception as e:
        logger.error("保存对话数据失败: %s", e)
    finally:
        await db.close()
