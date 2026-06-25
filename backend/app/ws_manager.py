"""WebSocket 连接管理器，用于广播文档处理状态。"""

import asyncio
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WSManager:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)
        logger.info("WS 连接加入，当前连接数: %d", len(self._connections))

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)
        logger.info("WS 连接断开，当前连接数: %d", len(self._connections))

    async def broadcast(self, message: dict):
        """向所有连接广播消息。"""
        if not self._connections:
            return
        data = json.dumps(message, ensure_ascii=False)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)


# 全局单例
manager = WSManager()


async def broadcast_doc_status(
    doc_id: int,
    status: str,
    step: str,
    chunk_count: int = 0,
    error: str | None = None,
):
    """广播文档状态变更。"""
    msg = {
        "type": "doc_status",
        "doc_id": doc_id,
        "status": status,
        "step": step,
        "chunk_count": chunk_count,
    }
    if error:
        msg["error"] = error
    await manager.broadcast(msg)
