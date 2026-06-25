"""Pydantic 数据模型。"""

from typing import Literal

from pydantic import BaseModel


# ── 请求模型 ──

class ChatRequest(BaseModel):
    """对话请求。"""
    session_id: str = ""
    message: str


class SessionCreate(BaseModel):
    """创建会话请求。"""
    title: str | None = None


# ── 引用来源 ──

class SourceInfo(BaseModel):
    """RAG 检索命中的文档来源。"""
    index: int          # 编号，从 1 开始
    title: str          # 文档标题
    filename: str       # 源文件名
    content: str        # 命中的子块内容


# ── SSE 流式响应 ──

class ChatChunk(BaseModel):
    """SSE 流式返回的每一帧。"""
    type: Literal["reasoning", "content", "references", "done", "error"]
    text: str = ""
    sources: list[SourceInfo] | None = None


# ── 响应模型 ──

class SessionInfo(BaseModel):
    """会话信息。"""
    id: str
    title: str
    message_count: int
    created_at: str
    updated_at: str


class MessageInfo(BaseModel):
    """消息信息。"""
    id: int
    role: str
    content: str
    reasoning_content: str | None = None
    references: list[SourceInfo] | None = None
    created_at: str


class KnowledgeDocInfo(BaseModel):
    """知识库文档信息。"""
    id: int
    filename: str
    file_type: str
    chunk_count: int
    status: str
    created_at: str


class StatsOverview(BaseModel):
    """统计总览。"""
    total_sessions: int
    total_messages: int
    total_docs: int
    kb_hit_rate: float


class TopQuestion(BaseModel):
    """热门问题。"""
    question: str
    count: int


class ApiResponse(BaseModel):
    """统一 API 响应格式。"""
    code: int = 0
    data: object | None = None
    msg: str = "ok"
