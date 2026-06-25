"""Mimo-v2.5 LLM 调用封装。"""

import json
from collections.abc import AsyncGenerator

import httpx

from app.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }


async def chat_completion_stream(
    messages: list[dict],
) -> AsyncGenerator[dict, None]:
    """流式调用 LLM，yield 每个 SSE chunk。

    返回的 dict 格式：
    - {"type": "reasoning", "text": "..."}  推理过程
    - {"type": "content", "text": "..."}    最终回答
    - {"type": "done", "text": ""}
    """
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": LLM_TEMPERATURE,
        "stream": True,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream(
            "POST",
            f"{LLM_BASE_URL}/chat/completions",
            headers=_headers(),
            json=payload,
        ) as response:
            response.raise_for_status()
            buffer = ""
            async for chunk in response.aiter_text():
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        yield {"type": "done", "text": ""}
                        return
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        # 推理内容
                        reasoning = delta.get("reasoning_content")
                        if reasoning:
                            yield {"type": "reasoning", "text": reasoning}
                        # 正文内容
                        content = delta.get("content")
                        if content:
                            yield {"type": "content", "text": content}
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue


async def chat_completion_text(
    messages: list[dict],
    *,
    max_tokens: int = 64,
    temperature: float = 0,
) -> str:
    """非流式调用 LLM，返回 message.content。"""
    payload = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=_headers(),
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"].get("content", "")


async def warmup() -> None:
    """预热 LLM 服务，避免首次用户请求承担 Ollama 模型加载。"""
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": "你好"}],
        "max_tokens": 1,
        "temperature": 0,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{LLM_BASE_URL}/chat/completions",
            headers=_headers(),
            json=payload,
        )
        response.raise_for_status()
