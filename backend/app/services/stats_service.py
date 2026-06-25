"""统计查询服务。"""

from app.db.database import get_db


async def get_overview() -> dict:
    """统计总览：总会话数、总消息数、文档数、命中率。"""
    db = await get_db()
    try:
        # 总会话数
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM sessions")
        row = await cursor.fetchone()
        total_sessions = row["cnt"]

        # 总消息数
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM messages")
        row = await cursor.fetchone()
        total_messages = row["cnt"]

        # 文档数（ready 状态）
        cursor = await db.execute("SELECT COUNT(*) as cnt FROM knowledge_docs WHERE status = 'ready'")
        row = await cursor.fetchone()
        total_docs = row["cnt"]

        # 命中率
        cursor = await db.execute("SELECT COUNT(*) as total, SUM(kb_hit) as hits FROM qa_logs")
        row = await cursor.fetchone()
        total = row["total"] or 0
        hits = row["hits"] or 0
        kb_hit_rate = round(hits / total * 100, 1) if total > 0 else 0.0

        return {
            "total_sessions": total_sessions,
            "total_messages": total_messages,
            "total_docs": total_docs,
            "kb_hit_rate": kb_hit_rate,
        }
    finally:
        await db.close()


async def get_top_questions(limit: int = 10, days: int = 7) -> list[dict]:
    """获取热门问题 Top N。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT user_question as question, COUNT(*) as count "
            "FROM qa_logs "
            "WHERE created_at >= datetime('now', ? || ' days') "
            "GROUP BY user_question "
            "ORDER BY count DESC "
            "LIMIT ?",
            (f"-{days}", limit),
        )
        rows = await cursor.fetchall()
        return [{"question": row["question"], "count": row["count"]} for row in rows]
    finally:
        await db.close()
