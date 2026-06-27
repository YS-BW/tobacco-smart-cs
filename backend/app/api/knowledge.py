"""知识库管理接口。"""

import asyncio
import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from app.config import PROCESSED_DIR, RAW_DIR
from app.db.database import get_db, get_write_lock
from app.models.schemas import ApiResponse, KnowledgeDocInfo
from app.services.document_processor import enqueue_document
from app.services.knowledge import delete_document, process_document
from app.utils.helpers import detect_file_type, now_iso
from app.ws_manager import manager

router = APIRouter()

ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "png", "jpg", "jpeg", "webp", "md", "html", "htm"}


async def _save_file(raw_path: Path, file: UploadFile):
    """在线程池中保存文件，避免阻塞事件循环。"""
    def _write():
        with open(raw_path, "wb") as out:
            shutil.copyfileobj(file.file, out)
    await asyncio.to_thread(_write)


@router.post("/knowledge/upload", status_code=201)
async def upload_files(files: list[UploadFile]):
    """上传文件到知识库，立即返回，后台异步处理。"""
    if not files:
        raise HTTPException(status_code=400, detail="未上传任何文件")

    Path(RAW_DIR).mkdir(parents=True, exist_ok=True)

    docs = []
    skipped = []
    db = await get_db()
    write_lock = get_write_lock()
    try:
        for f in files:
            ext = f.filename.rsplit(".", 1)[-1].lower() if "." in (f.filename or "") else ""
            if ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(status_code=400, detail=f"不支持的文件格式: .{ext}")

            # 去重：同名文件已存在则跳过
            async with write_lock:
                cursor = await db.execute(
                    "SELECT id FROM knowledge_docs WHERE filename = ?", (f.filename,)
                )
                existing = await cursor.fetchone()
            if existing is not None:
                skipped.append(f.filename)
                continue

            file_type = detect_file_type(f.filename)
            ts = now_iso()

            # 异步写文件，不阻塞事件循环
            raw_path = Path(RAW_DIR) / f.filename
            await _save_file(raw_path, f)

            # 插入数据库记录
            async with write_lock:
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

            # 上传接口只负责落盘和入队，解析/向量化由后台 worker 执行。
            await enqueue_document(str(raw_path), doc_id, f.filename, file_type, process_document)

    finally:
        await db.close()

    msg = f"{len(docs)} 个文件已提交处理"
    if skipped:
        msg += f"，{len(skipped)} 个重复跳过"
    return ApiResponse(data={"message": msg, "docs": docs, "skipped": skipped})


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


@router.get("/knowledge/content/{filename:path}")
async def get_document_content(filename: str):
    """获取知识库文档的完整 Markdown 内容。"""
    file_path = Path(PROCESSED_DIR) / filename
    # 处理后的文件统一存为 .md，尝试用 .md 后缀查找
    if not file_path.is_file():
        md_path = Path(PROCESSED_DIR) / f"{Path(filename).stem}.md"
        if md_path.is_file():
            file_path = md_path
        else:
            raise HTTPException(status_code=404, detail="文档不存在")
    content = file_path.read_text(encoding="utf-8")
    return ApiResponse(data={"filename": filename, "content": content})


@router.post("/knowledge/retry-failed")
async def retry_failed():
    """重新处理所有失败的文档。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, filename, file_type FROM knowledge_docs WHERE status = 'failed'"
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    if not rows:
        return ApiResponse(data={"message": "没有失败的文档", "retried": 0})

    retried = 0
    for r in rows:
        raw_path = Path(RAW_DIR) / r["filename"]
        if not raw_path.is_file():
            continue
        async with get_write_lock():
            wdb = await get_db()
            try:
                await wdb.execute(
                    "UPDATE knowledge_docs SET status = 'processing', error_msg = NULL WHERE id = ?",
                    (r["id"],),
                )
                await wdb.commit()
            finally:
                await wdb.close()
        await enqueue_document(str(raw_path), r["id"], r["filename"], r["file_type"], process_document)
        retried += 1

    return ApiResponse(data={"message": f"已重新提交 {retried} 个文档", "retried": retried})


@router.post("/knowledge/requeue-stuck")
async def requeue_stuck():
    """将卡在 processing 状态的文档重新入队（后端重启后队列丢失）。"""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, filename, file_type FROM knowledge_docs WHERE status = 'processing'"
        )
        rows = await cursor.fetchall()
    finally:
        await db.close()

    if not rows:
        return ApiResponse(data={"message": "没有卡住的文档", "requeued": 0})

    requeued = 0
    for r in rows:
        raw_path = Path(RAW_DIR) / r["filename"]
        if not raw_path.is_file():
            continue
        await enqueue_document(str(raw_path), r["id"], r["filename"], r["file_type"], process_document)
        requeued += 1

    return ApiResponse(data={"message": f"已重新入队 {requeued} 个文档", "requeued": requeued})


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
