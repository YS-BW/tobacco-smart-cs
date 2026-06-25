"""知识库管理接口。"""

import asyncio
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from app.config import RAW_DIR
from app.db.database import get_db
from app.models.schemas import ApiResponse, KnowledgeDocInfo
from app.services.knowledge import delete_document, process_document
from app.utils.helpers import detect_file_type, now_iso
from app.ws_manager import manager

router = APIRouter()

# 支持的文件格式
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "png", "jpg", "jpeg", "webp", "md"}


@router.post("/knowledge/upload", status_code=201)
async def upload_files(files: list[UploadFile]):
    """上传文件到知识库，异步处理。"""
    if not files:
        raise HTTPException(status_code=400, detail="未上传任何文件")

    Path(RAW_DIR).mkdir(parents=True, exist_ok=True)

    docs = []
    db = await get_db()
    try:
        for f in files:
            # 校验格式
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in (f.filename or "") else ""
            if ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"不支持的文件格式: .{ext}")

            file_type = detect_file_type(f.filename)
            ts = now_iso()

            # 存文件到 data/raw/
            raw_path = Path(RAW_DIR) / f.filename
            with open(raw_path, "wb") as out:
                shutil.copyfileobj(f.file, out)

            # 插入数据库记录
            cursor = await db.execute(
                "INSERT INTO knowledge_docs (filename, file_type, status, created_at) VALUES (?, ?, 'processing', ?)",
                (f.filename, file_type, ts),
            )
            await db.commit()
            doc_id = cursor.lastrowid

            docs.append(KnowledgeDocInfo(
                id=doc_id, filename=f.filename, file_type=file_type,
                chunk_count=0, status="processing", created_at=ts,
            ))

            # 后台异步处理
            asyncio.create_task(_process_in_background(str(raw_path), doc_id, f.filename, file_type))

    finally:
        await db.close()

    return ApiResponse(data={"message": f"{len(docs)} 个文件已提交处理", "docs": docs})


async def _process_in_background(file_path: str, doc_id: int, filename: str, file_type: str):
    """后台处理文档：解析 → 分块 → 向量化。"""
    try:
        await process_document(file_path, doc_id, filename, file_type)
    except Exception as e:
        # process_document 内部已更新状态为 failed
        pass


@router.get("/knowledge/documents")
async def list_documents():
    """获取知识库文档列表。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, filename, file_type, chunk_count, status, created_at "
            "FROM knowledge_docs ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        docs = [
            KnowledgeDocInfo(
                id=r["id"], filename=r["filename"], file_type=r["file_type"],
                chunk_count=r["chunk_count"], status=r["status"], created_at=r["created_at"],
            )
            for r in rows
        ]
        return ApiResponse(data=docs)
    finally:
        await db.close()


@router.websocket("/ws/knowledge")
async def ws_knowledge(ws: WebSocket):
    """知识库文档处理状态 WebSocket 推送。"""
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # 保持连接
    except WebSocketDisconnect:
        manager.disconnect(ws)


@router.delete("/knowledge/documents/{doc_id}", status_code=204)
async def delete_doc(doc_id: int):
    """删除文档及 ChromaDB 中的向量数据。"""
    db = await get_db()
    try:
        cursor = await db.execute("SELECT id FROM knowledge_docs WHERE id = ?", (doc_id,))
        if (await cursor.fetchone()) is None:
            raise HTTPException(status_code=404, detail="文档不存在")

        await db.execute("DELETE FROM knowledge_docs WHERE id = ?", (doc_id,))
        await db.commit()
    finally:
        await db.close()

    # 删除 ChromaDB 中的向量
    await delete_document(doc_id)
