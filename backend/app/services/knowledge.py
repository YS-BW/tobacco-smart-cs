"""知识库文档处理服务：MinerU 解析 → 分块 → 向量化 → 入库。"""

import json
import logging
import subprocess
import sys
from pathlib import Path

import chromadb

from app.config import (
    MINERU_TOKEN, MINERU_SCRIPT,
    RAW_DIR, PROCESSED_DIR,
    CHROMA_PERSIST_DIR, CHROMA_COLLECTION,
    CHUNK_MAX_SIZE, CHUNK_TARGET_SIZE,
)
from app.services import embedding_service
from app.db.database import get_db

logger = logging.getLogger(__name__)

def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return client.get_or_create_collection(CHROMA_COLLECTION)


def parse_with_mineru(file_path: str) -> str:
    """调用 MinerU 解析文件，返回 Markdown 内容。"""
    result = subprocess.run(
        [sys.executable, MINERU_SCRIPT, file_path, "--stdout", "--api", "standard"],
        capture_output=True,
        text=True,
        timeout=300,
        env={"MINERU_TOKEN": MINERU_TOKEN, "PATH": "/usr/bin:/usr/local/bin:/opt/homebrew/bin"},
    )
    if result.returncode != 0:
        raise RuntimeError(f"MinerU 解析失败: {result.stderr}")
    return result.stdout


def split_markdown(markdown_text: str, doc_id: int, filename: str) -> list[dict]:
    """按标题层级结构化分块。

    策略：
    - 子块（检索用）：按 ### (H3) 切分
    - 父块（给 LLM）：按 ## (H2) 切分
    - 超过 CHUNK_MAX_SIZE 的子块按段落二次切分
    """
    lines = markdown_text.split("\n")
    chunks = []

    # 解析出标题层级结构
    current_h2 = ""
    current_h2_content = ""
    current_h3 = ""
    current_h3_content = ""

    def flush_h3(chunk_index: int) -> int:
        """将当前 H3 块保存为 chunk。"""
        nonlocal current_h3_content
        if not current_h3_content.strip():
            return chunk_index

        text = current_h3_content.strip()
        # 超长块按段落二次切分
        if len(text) > CHUNK_MAX_SIZE:
            paragraphs = text.split("\n\n")
            sub_text = ""
            for para in paragraphs:
                if len(sub_text) + len(para) > CHUNK_TARGET_SIZE and sub_text:
                    chunks.append(_make_chunk(doc_id, chunk_index, filename, current_h2, current_h3, sub_text.strip(), current_h2_content.strip()))
                    chunk_index += 1
                    sub_text = para
                else:
                    sub_text += "\n\n" + para if sub_text else para
            if sub_text.strip():
                chunks.append(_make_chunk(doc_id, chunk_index, filename, current_h2, current_h3, sub_text.strip(), current_h2_content.strip()))
                chunk_index += 1
        else:
            chunks.append(_make_chunk(doc_id, chunk_index, filename, current_h2, current_h3, text, current_h2_content.strip()))
            chunk_index += 1

        current_h3_content = ""
        return chunk_index

    chunk_index = 0

    for line in lines:
        # 检测 H2 标题
        if line.startswith("## ") and not line.startswith("### "):
            # 先把当前 H3 flush 掉
            chunk_index = flush_h3(chunk_index)
            current_h2 = line.strip()
            current_h2_content = line + "\n"
            current_h3 = ""
            current_h3_content = ""
        # 检测 H3 标题
        elif line.startswith("### "):
            chunk_index = flush_h3(chunk_index)
            current_h3 = line.strip()
            current_h3_content = line + "\n"
            current_h2_content += line + "\n"
        else:
            current_h3_content += line + "\n"
            current_h2_content += line + "\n"

    # flush 最后一个块
    chunk_index = flush_h3(chunk_index)

    # 如果没有任何 H3 标题，把整个文档作为一个 chunk
    if not chunks and markdown_text.strip():
        chunks.append({
            "chunk_id": f"doc_{doc_id}_chunk_0",
            "content": markdown_text.strip()[:CHUNK_MAX_SIZE],
            "parent_content": markdown_text.strip(),
            "metadata": {
                "source": filename,
                "doc_id": doc_id,
                "heading_path": filename,
                "chunk_index": 0,
            },
        })

    return chunks


def _make_chunk(doc_id: int, chunk_index: int, filename: str, h2: str, h3: str, content: str, parent_content: str) -> dict:
    heading_path = f"{filename} > {h2}" + (f" > {h3}" if h3 else "")
    return {
        "chunk_id": f"doc_{doc_id}_chunk_{chunk_index}",
        "content": content,
        "parent_content": parent_content,
        "metadata": {
            "source": filename,
            "doc_id": doc_id,
            "heading_path": heading_path,
            "chunk_index": chunk_index,
        },
    }


async def process_document(file_path: str, doc_id: int, filename: str, file_type: str) -> int:
    """处理文档：解析 → 分块 → 向量化 → 入库。返回分块数量。"""
    from app.ws_manager import broadcast_doc_status

    db = await get_db()
    try:
        # 1. 解析为 Markdown
        await broadcast_doc_status(doc_id, "processing", "解析中")
        if file_type == "markdown":
            markdown_text = Path(file_path).read_text(encoding="utf-8")
        else:
            markdown_text = parse_with_mineru(file_path)

        # 保存 Markdown
        processed_path = Path(PROCESSED_DIR) / f"{Path(filename).stem}.md"
        processed_path.write_text(markdown_text, encoding="utf-8")

        # 2. 分块
        await broadcast_doc_status(doc_id, "processing", "分块中")
        chunks = split_markdown(markdown_text, doc_id, filename)
        if not chunks:
            await db.execute(
                "UPDATE knowledge_docs SET status = 'failed', error_msg = '分块结果为空' WHERE id = ?",
                (doc_id,),
            )
            await db.commit()
            await broadcast_doc_status(doc_id, "failed", "分块失败", error="分块结果为空")
            return 0

        # 3. 向量化并入库
        await broadcast_doc_status(doc_id, "processing", "向量化中", chunk_count=len(chunks))
        collection = _get_collection()

        ids = [c["chunk_id"] for c in chunks]
        documents = [c["content"] for c in chunks]
        embeddings = embedding_service.encode_documents(documents)
        metadatas = []
        for c in chunks:
            meta = c["metadata"].copy()
            meta["parent_content"] = c["parent_content"]
            metadatas.append(meta)

        collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)

        # 4. 更新数据库状态
        await db.execute(
            "UPDATE knowledge_docs SET status = 'ready', chunk_count = ? WHERE id = ?",
            (len(chunks), doc_id),
        )
        await db.commit()
        await broadcast_doc_status(doc_id, "ready", "完成", chunk_count=len(chunks))
        logger.info("文档处理完成: %s chunks=%d", filename, len(chunks))
        return len(chunks)

    except Exception as e:
        logger.error("文档处理失败: %s error=%s", filename, e)
        await db.execute(
            "UPDATE knowledge_docs SET status = 'failed', error_msg = ? WHERE id = ?",
            (str(e)[:500], doc_id),
        )
        await db.commit()
        await broadcast_doc_status(doc_id, "failed", "处理失败", error=str(e)[:200])
        raise
    finally:
        await db.close()


async def delete_document(doc_id: int) -> None:
    """从 ChromaDB 删除指定文档的所有 chunk。"""
    collection = _get_collection()
    # 通过 metadata 过滤删除
    try:
        collection.delete(where={"doc_id": doc_id})
    except Exception:
        pass  # collection 可能为空
