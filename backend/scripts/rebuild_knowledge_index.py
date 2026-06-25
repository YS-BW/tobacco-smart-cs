"""Rebuild Chroma knowledge vectors from processed Markdown files.

Usage:
    uv run python scripts/rebuild_knowledge_index.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import chromadb

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import CHROMA_COLLECTION, CHROMA_PERSIST_DIR, PROCESSED_DIR
from app.db.database import get_db, init_db
from app.services import embedding_service
from app.services.knowledge import split_markdown
from app.utils.helpers import now_iso


def _get_fresh_collection():
    """Delete and recreate the Chroma collection."""
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    try:
        client.delete_collection(CHROMA_COLLECTION)
    except Exception:
        pass
    return client.get_or_create_collection(CHROMA_COLLECTION)


async def rebuild(processed_dir: str | Path = PROCESSED_DIR) -> tuple[int, int]:
    """Rebuild knowledge_docs and Chroma vectors from processed Markdown files."""
    processed_path = Path(processed_dir)
    markdown_files = sorted(processed_path.glob("*.md"))

    await init_db()
    collection = _get_fresh_collection()
    db = await get_db()
    total_chunks = 0

    try:
        await db.execute("DELETE FROM knowledge_docs")
        await db.commit()

        for markdown_file in markdown_files:
            ts = now_iso()
            cursor = await db.execute(
                "INSERT INTO knowledge_docs (filename, file_type, status, created_at) VALUES (?, 'markdown', 'processing', ?)",
                (markdown_file.name, ts),
            )
            await db.commit()
            doc_id = cursor.lastrowid

            markdown_text = markdown_file.read_text(encoding="utf-8")
            chunks = split_markdown(markdown_text, doc_id, markdown_file.name)
            if not chunks:
                await db.execute(
                    "UPDATE knowledge_docs SET status = 'failed', error_msg = '分块结果为空' WHERE id = ?",
                    (doc_id,),
                )
                await db.commit()
                continue

            ids = [chunk["chunk_id"] for chunk in chunks]
            documents = [chunk["content"] for chunk in chunks]
            embeddings = embedding_service.encode_documents(documents)
            metadatas = []
            for chunk in chunks:
                meta = chunk["metadata"].copy()
                meta["parent_content"] = chunk["parent_content"]
                metadatas.append(meta)

            collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
            await db.execute(
                "UPDATE knowledge_docs SET status = 'ready', chunk_count = ? WHERE id = ?",
                (len(chunks), doc_id),
            )
            await db.commit()
            total_chunks += len(chunks)
            print(f"indexed {markdown_file.name}: {len(chunks)} chunks")

    finally:
        await db.close()

    return len(markdown_files), total_chunks


async def _main() -> None:
    doc_count, chunk_count = await rebuild()
    print(f"rebuild complete: {doc_count} docs, {chunk_count} chunks")


if __name__ == "__main__":
    asyncio.run(_main())
