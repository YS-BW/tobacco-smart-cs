"""Knowledge document processing service tests."""

import json

from app.db import database
from app.db.database import get_db, init_db
from app.services import knowledge


def test_clean_mineru_markdown_unwraps_sup_and_sub_tags():
    """清理 MinerU 残留的上下标 HTML 标签，同时保留正文。"""
    markdown = "国烟<sup>[1][2]</sup>。\n上<sub>海开设了卷烟厂。[3]</sub>"

    cleaned = knowledge.clean_mineru_markdown(markdown)

    assert "<sup>" not in cleaned
    assert "</sup>" not in cleaned
    assert "<sub>" not in cleaned
    assert "</sub>" not in cleaned
    assert "国烟[1][2]" in cleaned
    assert "上海开设了卷烟厂。[3]" in cleaned


def test_clean_mineru_markdown_converts_html_tables_to_text_rows():
    """清理 MinerU 残留的 HTML 表格标签，同时保留可检索的表格文本。"""
    markdown = (
        "产品列表\n"
        "<table><tr><td>產品</td><td>生產商</td></tr>"
        "<tr><td>IQOS</td><td>菲利普莫里斯國際(PMI)</td></tr>"
        "<tr><td>lil</td><td>KT&amp;G</td></tr></table>"
    )

    cleaned = knowledge.clean_mineru_markdown(markdown)

    assert "<table" not in cleaned
    assert "<tr" not in cleaned
    assert "<td" not in cleaned
    assert "</" not in cleaned
    assert "產品 | 生產商" in cleaned
    assert "IQOS | 菲利普莫里斯國際(PMI)" in cleaned
    assert "lil | KT&G" in cleaned


def test_mineru_fallback_markdown_uses_content_list_text(tmp_path):
    """MinerU Markdown 为空时，应能从结构化 content_list 提取文字。"""
    output_dir = tmp_path / "output"
    doc_dir = output_dir / "香港煙草有限公司"
    doc_dir.mkdir(parents=True)
    (doc_dir / "task_content_list.json").write_text(
        json.dumps(
            [
                {"type": "header", "text": "維基百科自由的百科全書"},
                {"type": "header", "text": "香港煙草有限公司"},
                {
                    "type": "header",
                    "text": "香港煙草有限公司是香港一家製造及銷售香煙的公司。",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    markdown = knowledge.mineru_fallback_markdown(
        str(tmp_path / "raw" / "香港煙草有限公司.pdf"),
        output_dir,
    )

    assert "香港煙草有限公司" in markdown
    assert "製造及銷售香煙" in markdown
    assert markdown.count("\n\n") >= 2


async def test_process_document_clears_previous_error_on_success(monkeypatch, tmp_path):
    """失败文档重试成功后，应清空旧 error_msg。"""
    monkeypatch.setattr(database, "SQLITE_DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setattr(knowledge, "PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setattr(knowledge.embedding_service, "encode_documents", lambda docs: [[0.1] for _ in docs])
    monkeypatch.setattr(knowledge, "_add_to_collection", lambda *args: None)
    await init_db()

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO knowledge_docs (id, filename, file_type, status, error_msg, created_at) "
            "VALUES (1, 'retry.md', 'markdown', 'failed', '分块结果为空', '2026-06-26T00:00:00Z')"
        )
        await db.commit()
    finally:
        await db.close()

    raw_path = tmp_path / "retry.md"
    raw_path.write_text("# retry\n\n正文内容", encoding="utf-8")

    chunks = await knowledge.process_document(str(raw_path), 1, "retry.md", "markdown")

    db = await get_db()
    try:
        row = await (
            await db.execute("SELECT status, chunk_count, error_msg FROM knowledge_docs WHERE id = 1")
        ).fetchone()
    finally:
        await db.close()

    assert chunks == 1
    assert row["status"] == "ready"
    assert row["chunk_count"] == 1
    assert row["error_msg"] is None


async def test_process_document_cleans_markdown_before_indexing(monkeypatch, tmp_path):
    """直接上传 Markdown 时，也应清理 HTML 标签后再保存和入库。"""
    indexed_documents: list[str] = []

    monkeypatch.setattr(database, "SQLITE_DB_PATH", str(tmp_path / "chat.db"))
    monkeypatch.setattr(knowledge, "PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setattr(knowledge.embedding_service, "encode_documents", lambda docs: [[0.1] for _ in docs])
    monkeypatch.setattr(knowledge, "_add_to_collection", lambda ids, docs, embeddings, metadatas: indexed_documents.extend(docs))
    await init_db()

    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO knowledge_docs (id, filename, file_type, status, created_at) "
            "VALUES (1, 'table.md', 'markdown', 'processing', '2026-06-26T00:00:00Z')"
        )
        await db.commit()
    finally:
        await db.close()

    raw_path = tmp_path / "table.md"
    raw_path.write_text(
        "## 产品\n\n<table><tr><td>产品</td><td>生产商</td></tr><tr><td>IQOS</td><td>PMI</td></tr></table>",
        encoding="utf-8",
    )

    chunks = await knowledge.process_document(str(raw_path), 1, "table.md", "markdown")
    processed_text = (tmp_path / "processed" / "table.md").read_text(encoding="utf-8")

    assert chunks == 1
    assert "<table" not in processed_text
    assert "<td" not in processed_text
    assert "产品 | 生产商" in processed_text
    assert "IQOS | PMI" in processed_text
    assert indexed_documents
    assert all("<table" not in doc and "<td" not in doc for doc in indexed_documents)
