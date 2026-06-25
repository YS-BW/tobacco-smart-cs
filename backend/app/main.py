"""FastAPI 应用入口。"""

import asyncio
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import chat, knowledge, stats
from app.config import MODEL_WARMUP_ENABLED, RAG_WARMUP_QUERY
from app.db.database import init_db
from app.services import llm_service, rag_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="烟草智能客服系统", version="0.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由挂载
app.include_router(chat.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(stats.router, prefix="/api")


@app.on_event("startup")
async def startup():
    """启动时初始化数据库。"""
    await init_db()
    if MODEL_WARMUP_ENABLED:
        await warmup_models()


async def warmup_models() -> None:
    """预热 DashScope RAG 和 LLM，避免首次请求承担初始化成本。"""
    try:
        logger.info("开始预热 RAG 模型...")
        await asyncio.to_thread(rag_service.warmup, RAG_WARMUP_QUERY)
        logger.info("RAG 模型预热完成")
    except Exception as e:
        logger.warning("RAG 模型预热失败: %s", e)

    try:
        logger.info("开始预热 LLM 模型...")
        await llm_service.warmup()
        logger.info("LLM 模型预热完成")
    except Exception as e:
        logger.warning("LLM 模型预热失败: %s", e)


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")
