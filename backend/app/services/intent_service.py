"""Use the main LLM to decide whether a user turn needs RAG."""

from __future__ import annotations

import json
import logging
import re

from app.services import llm_service

logger = logging.getLogger(__name__)

INTENT_PROMPT = """你是一个烟草行业客服系统的 RAG 路由器。
请判断用户这轮消息是否需要查询烟草知识库。

必须查询知识库的情况：
- 询问烟草产品参数、价格、焦油量、真假鉴别、许可证、经营规范、种植加工等事实问题
- 当前问题是短句追问，但结合上一轮问题后仍然在问烟草行业事实

不需要查询知识库的情况：
- 问候、寒暄、感谢、告别
- 询问你是谁、你能做什么、介绍你自己
- 普通闲聊或不需要烟草知识库即可回答的问题

只输出 JSON，不要解释：
{"use_rag": true}
或
{"use_rag": false}
"""


async def should_use_rag(*, user_message: str, retrieval_query: str) -> bool:
    """Return whether this turn should query the knowledge base."""
    messages = [
        {"role": "system", "content": INTENT_PROMPT},
        {
            "role": "user",
            "content": (
                f"用户原始消息：{user_message}\n"
                f"结合上下文后的检索问题：{retrieval_query}"
            ),
        },
    ]

    try:
        content = await llm_service.chat_completion_text(messages, max_tokens=32, temperature=0)
        return _parse_use_rag(content)
    except Exception as e:
        logger.warning("意图识别失败，默认走 RAG: %s", e)
        return True


def _parse_use_rag(content: str) -> bool:
    """Parse a strict or fenced JSON intent response."""
    match = re.search(r"\{.*?\}", content, flags=re.S)
    if not match:
        raise ValueError(f"intent JSON not found: {content[:80]}")
    data = json.loads(match.group(0))
    value = data.get("use_rag")
    if not isinstance(value, bool):
        raise ValueError(f"intent use_rag is not boolean: {content[:80]}")
    return value
