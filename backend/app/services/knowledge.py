"""知识库文档处理服务：MinerU 解析 → 分块 → 向量化 → 入库。"""

import asyncio
import html
import json
import logging
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import chromadb

from app.config import (
    MINERU_TOKEN, MINERU_SCRIPT, MINERU_OUTPUT_DIR,
    PROCESSED_DIR,
    CHROMA_PERSIST_DIR, CHROMA_COLLECTION,
    CHUNK_MAX_SIZE, CHUNK_TARGET_SIZE,
)
from app.services import embedding_service
from app.db.database import get_db, get_write_lock

logger = logging.getLogger(__name__)

MINERU_CONTENT_PATTERNS = (
    "*_content_list.json",
    "content_list.json",
    "*_content_list_v2.json",
    "content_list_v2.json",
)
MINERU_TEXT_TYPES = {"text", "header", "page_header", "title", "paragraph"}
MINERU_INLINE_HTML_TAG_RE = re.compile(r"</?(?:sup|sub)\b[^>]*>", re.IGNORECASE)
MINERU_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
MINERU_BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
MINERU_REMAINING_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")


class _TableTextParser(HTMLParser):
    """将 MinerU 的 HTML 表格转换成按行分隔的纯文本。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"}:
            self._current_cell = []
        elif tag == "br" and self._current_cell is not None:
            self._current_cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._current_cell is not None:
            cell_text = " ".join("".join(self._current_cell).split())
            if cell_text and self._current_row is not None:
                self._current_row.append(cell_text)
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None

    def to_text(self) -> str:
        return "\n".join(" | ".join(row) for row in self.rows).strip()

def _get_collection():
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return client.get_or_create_collection(CHROMA_COLLECTION)


def _add_to_collection(ids: list[str], documents: list[str], embeddings: list[list[float]], metadatas: list[dict]) -> None:
    collection = _get_collection()
    collection.add(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)


def _delete_from_collection(doc_id: int) -> None:
    collection = _get_collection()
    collection.delete(where={"doc_id": doc_id})


def parse_with_mineru(file_path: str, max_retries: int = 3) -> str:
    """调用 MinerU 解析文件，返回 Markdown 内容。带重试机制。"""
    import time

    Path(MINERU_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    for attempt in range(max_retries):
        result = subprocess.run(
            [
                sys.executable,
                MINERU_SCRIPT,
                file_path,
                "--stdout",
                "--api",
                "standard",
                "--output",
                MINERU_OUTPUT_DIR,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            env={"MINERU_TOKEN": MINERU_TOKEN, "PATH": "/usr/bin:/usr/local/bin:/opt/homebrew/bin"},
        )
        if result.returncode == 0:
            if result.stdout.strip():
                return result.stdout
            break

        # API 限流错误，等待后重试
        if "code -60024" in result.stderr and attempt < max_retries - 1:
            wait = 15 * (2 ** attempt)
            logger.warning("MinerU 限流，%ds 后重试 (%d/%d): %s", wait, attempt + 1, max_retries, file_path)
            time.sleep(wait)
            continue

        raise RuntimeError(f"MinerU 解析失败: {result.stderr}")

    fallback = mineru_fallback_markdown(file_path)
    if fallback:
        logger.warning("MinerU Markdown 为空，已从结构化结果兜底提取文本: %s", file_path)
        return fallback
    return result.stdout


def clean_mineru_markdown(markdown_text: str) -> str:
    """去掉 MinerU 残留的 HTML 标签，保留可检索正文。"""
    cleaned = MINERU_TABLE_RE.sub(_html_table_to_text, markdown_text)
    cleaned = MINERU_INLINE_HTML_TAG_RE.sub("", cleaned)
    cleaned = MINERU_BR_TAG_RE.sub("\n", cleaned)
    cleaned = MINERU_REMAINING_HTML_TAG_RE.sub(" ", cleaned)
    return html.unescape(cleaned)


def _html_table_to_text(match: re.Match) -> str:
    parser = _TableTextParser()
    parser.feed(match.group(0))
    table_text = parser.to_text()
    return f"\n{table_text}\n" if table_text else "\n"


def mineru_fallback_markdown(file_path: str, output_dir: str | Path | None = None) -> str:
    """从 MinerU 结构化 content list 中兜底提取 Markdown 文本。"""
    output_root = Path(output_dir) if output_dir is not None else Path(MINERU_OUTPUT_DIR)
    doc_dir = output_root / Path(file_path).stem
    if not doc_dir.is_dir():
        return ""

    seen_paths: set[Path] = set()
    for pattern in MINERU_CONTENT_PATTERNS:
        for path in sorted(doc_dir.glob(pattern)):
            if path in seen_paths or not path.is_file():
                continue
            seen_paths.add(path)
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            markdown = _content_items_to_markdown(_collect_mineru_text_items(data))
            if markdown:
                return markdown
    return ""


def _collect_mineru_text_items(node) -> list[dict]:
    items: list[dict] = []

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
            return

        if not isinstance(value, dict):
            return

        block_type = str(value.get("type") or "").lower()
        text_level = value.get("text_level")
        text = value.get("text")
        if isinstance(text, str) and text.strip() and (not block_type or block_type in MINERU_TEXT_TYPES):
            items.append({"type": block_type, "text": text.strip(), "text_level": text_level})

        content = value.get("content")
        if isinstance(content, str):
            if content.strip() and (not block_type or block_type in MINERU_TEXT_TYPES):
                items.append({"type": block_type, "text": content.strip(), "text_level": text_level})
        elif isinstance(content, (dict, list)):
            visit(content)

        for key, child in value.items():
            if key in {"text", "content", "bbox", "page_idx", "text_level"}:
                continue
            if isinstance(child, (dict, list)):
                visit(child)

    visit(node)
    return items


def _content_items_to_markdown(items: list[dict]) -> str:
    lines: list[str] = []
    previous = ""
    for index, item in enumerate(items):
        text = " ".join(str(item["text"]).split())
        if not text or text == previous:
            continue

        text_level = item.get("text_level")
        if isinstance(text_level, int):
            level = min(max(text_level, 1), 6)
            lines.append(f"{'#' * level} {text}")
        elif index == 0 and item.get("type") in {"header", "page_header", "title"}:
            lines.append(f"# {text}")
        else:
            lines.append(text)
        previous = text

    return "\n\n".join(lines).strip()


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


def _html_to_text_fallback(file_path: str) -> str:
    """MinerU 不可用时，从 HTML 中直接提取纯文本作为兜底。"""
    raw = Path(file_path).read_text(encoding="utf-8", errors="replace")
    # 移除 script/style 标签及内容
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    # 将 br/p/div/li/tr/h1-h6 转换为换行
    text = re.sub(r"<(?:br|BR)\s*/?>", "\n", text)
    text = re.sub(r"</(?:p|P|div|DIV|li|LI|tr|TR|h[1-6]|H[1-6])>", "\n", text)
    # 移除所有剩余标签
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    # 合并多余空行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_with_markitdown(file_path: str) -> str:
    """用 markitdown 本地解析文件为 Markdown（支持 HTML/PDF/DOCX/图片等）。"""
    from markitdown import MarkItDown
    md = MarkItDown()
    result = md.convert(file_path)
    return result.text_content


async def process_document(file_path: str, doc_id: int, filename: str, file_type: str) -> int:
    """处理文档：解析 → 分块 → 向量化 → 入库。返回分块数量。"""
    from app.ws_manager import broadcast_doc_status

    db = await get_db()
    write_lock = get_write_lock()
    try:
        # 1. 解析为 Markdown（默认走 markitdown，失败再 fallback MinerU）
        await broadcast_doc_status(doc_id, "processing", "解析中")
        if file_type == "markdown":
            markdown_text = await asyncio.to_thread(Path(file_path).read_text, encoding="utf-8")
        else:
            # markitdown 支持 HTML/PDF/DOCX/图片等，本地解析，快速且无限流
            try:
                markdown_text = await asyncio.to_thread(_parse_with_markitdown, file_path)
            except Exception as e:
                logger.warning("markitdown 解析失败，fallback 到 MinerU: %s error=%s", file_path, e)
                if file_type == "html":
                    markdown_text = await asyncio.to_thread(_html_to_text_fallback, file_path)
                else:
                    markdown_text = await asyncio.to_thread(parse_with_mineru, file_path)
        markdown_text = clean_mineru_markdown(markdown_text)

        # 保存 Markdown
        processed_path = Path(PROCESSED_DIR) / f"{Path(filename).stem}.md"
        await asyncio.to_thread(Path(PROCESSED_DIR).mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(processed_path.write_text, markdown_text, encoding="utf-8")

        # 2. 分块
        await broadcast_doc_status(doc_id, "processing", "分块中")
        chunks = await asyncio.to_thread(split_markdown, markdown_text, doc_id, filename)
        if not chunks:
            async with write_lock:
                await db.execute(
                    "UPDATE knowledge_docs SET status = 'failed', error_msg = '分块结果为空' WHERE id = ?",
                    (doc_id,),
                )
                await db.commit()
            await broadcast_doc_status(doc_id, "failed", "分块失败", error="分块结果为空")
            return 0

        # 3. 向量化并入库
        await broadcast_doc_status(doc_id, "processing", "向量化中", chunk_count=len(chunks))

        ids = [c["chunk_id"] for c in chunks]
        documents = [c["content"] for c in chunks]
        embeddings = await asyncio.to_thread(embedding_service.encode_documents, documents)
        metadatas = []
        for c in chunks:
            meta = c["metadata"].copy()
            meta["parent_content"] = c["parent_content"]
            metadatas.append(meta)

        await asyncio.to_thread(_add_to_collection, ids, documents, embeddings, metadatas)

        # 4. 更新数据库状态
        async with write_lock:
            await db.execute(
                "UPDATE knowledge_docs SET status = 'ready', chunk_count = ?, error_msg = NULL WHERE id = ?",
                (len(chunks), doc_id),
            )
            await db.commit()
        await broadcast_doc_status(doc_id, "ready", "完成", chunk_count=len(chunks))
        logger.info("文档处理完成: %s chunks=%d", filename, len(chunks))
        return len(chunks)

    except Exception as e:
        logger.error("文档处理失败: %s error=%s", filename, e)
        async with write_lock:
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
    # 通过 metadata 过滤删除
    try:
        await asyncio.to_thread(_delete_from_collection, doc_id)
    except Exception:
        pass  # collection 可能为空
