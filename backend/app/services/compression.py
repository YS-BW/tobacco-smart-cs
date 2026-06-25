"""上下文压缩服务。"""

import json
import logging

from app.db.database import get_db
from app.services import llm_service
from app.config import COMPRESSION_MAX_TOPIC_LENGTH

logger = logging.getLogger(__name__)

# 压缩 Prompt 模板
COMPRESSION_PROMPT = """请将以下多轮对话压缩为话题摘要列表。

要求：
1. 每轮对话（一问一答）压缩为一个话题
2. 每个话题不超过{max_len}个字
3. 保留关键信息：用户问了什么、得到了什么关键结论/数据
4. 按对话顺序输出
5. 严格输出JSON数组，不要输出其他内容

{dialogues}

输出格式（严格JSON数组）：
["话题1摘要", "话题2摘要", ...]"""


async def get_compressions(session_id: str) -> list[dict]:
    """查询指定会话已完成的压缩摘要，按轮次排序。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT round_start, round_end, compressed_topics "
            "FROM session_compressions "
            "WHERE session_id = ? AND status = 'done' "
            "ORDER BY round_start",
            (session_id,),
        )
        rows = await cursor.fetchall()
        return [
            {
                "round_start": row["round_start"],
                "round_end": row["round_end"],
                "topics": json.loads(row["compressed_topics"]),
            }
            for row in rows
        ]
    finally:
        await db.close()


async def compress_session(session_id: str, round_start: int, round_end: int) -> None:
    """异步压缩指定轮次的对话。

    调用 LLM 将 round_start~round_end 轮的对话压缩为话题摘要列表，
    存入 session_compressions 表。
    """
    db = await get_db()
    try:
        # 查询需要压缩的消息
        cursor = await db.execute(
            "SELECT role, content FROM messages "
            "WHERE session_id = ? "
            "ORDER BY id "
            "LIMIT ? OFFSET ?",
            (session_id, (round_end - round_start + 1) * 2, (round_start - 1) * 2),
        )
        rows = await cursor.fetchall()

        if not rows:
            logger.warning("压缩目标消息为空: session=%s range=%d-%d", session_id, round_start, round_end)
            return

        # 组装对话文本
        dialogues = []
        for i in range(0, len(rows) - 1, 2):
            user_msg = rows[i]["content"] if i < len(rows) else ""
            assistant_msg = rows[i + 1]["content"] if i + 1 < len(rows) else ""
            round_num = round_start + i // 2
            dialogues.append(f"第{round_num}轮：\nUser: {user_msg}\nAssistant: {assistant_msg}")

        prompt = COMPRESSION_PROMPT.format(
            max_len=COMPRESSION_MAX_TOPIC_LENGTH,
            dialogues="\n\n".join(dialogues),
        )

        # 调用 LLM 压缩
        messages = [{"role": "user", "content": prompt}]
        full_response = ""
        async for chunk in llm_service.chat_completion_stream(messages):
            if chunk["type"] == "content":
                full_response += chunk["text"]

        # 解析 JSON 数组
        topics = json.loads(full_response.strip())

        # 存入数据库
        await db.execute(
            "INSERT INTO session_compressions (session_id, compressed_topics, round_start, round_end, status) "
            "VALUES (?, ?, ?, ?, 'done')",
            (session_id, json.dumps(topics, ensure_ascii=False), round_start, round_end),
        )
        await db.commit()
        logger.info("压缩完成: session=%s range=%d-%d topics=%d", session_id, round_start, round_end, len(topics))

    except Exception as e:
        logger.error("压缩失败: session=%s range=%d-%d error=%s", session_id, round_start, round_end, e)
        # 记录失败状态
        try:
            await db.execute(
                "INSERT INTO session_compressions (session_id, compressed_topics, round_start, round_end, status) "
                "VALUES (?, '[]', ?, ?, 'failed')",
                (session_id, round_start, round_end),
            )
            await db.commit()
        except Exception:
            pass
    finally:
        await db.close()
