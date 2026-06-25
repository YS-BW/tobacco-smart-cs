"""Knowledge index rebuild script tests."""

import sqlite3
import subprocess
import sys

import pytest
import chromadb

from app.db import database


def test_rebuild_script_imports_when_executed_by_path():
    """The script should be importable when Python runs scripts/rebuild_knowledge_index.py directly."""
    code = (
        "import os, runpy, sys; "
        "sys.path = [p for p in sys.path if p not in ('', os.getcwd())]; "
        "sys.path.insert(0, 'scripts'); "
        "runpy.run_path('scripts/rebuild_knowledge_index.py', run_name='not_main')"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_rebuild_knowledge_index_recreates_docs_and_vectors(monkeypatch, tmp_path):
    """Rebuild should recreate knowledge_docs and Chroma vectors from processed markdown."""
    from scripts import rebuild_knowledge_index

    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    (processed_dir / "产品参数.md").write_text("## 参数\n\n### 黄鹤楼硬红\n\n焦油量 11mg/支。", encoding="utf-8")

    db_path = tmp_path / "chat.db"
    chroma_dir = tmp_path / "chroma"
    monkeypatch.setattr(database, "SQLITE_DB_PATH", str(db_path))
    monkeypatch.setattr(rebuild_knowledge_index, "CHROMA_PERSIST_DIR", str(chroma_dir))
    monkeypatch.setattr(
        rebuild_knowledge_index.embedding_service,
        "encode_documents",
        lambda documents: [[float(idx), 1.0] for idx, _ in enumerate(documents)],
    )

    doc_count, chunk_count = await rebuild_knowledge_index.rebuild(processed_dir)

    assert (doc_count, chunk_count) == (1, 1)
    with sqlite3.connect(db_path) as con:
        rows = con.execute("SELECT filename, status, chunk_count FROM knowledge_docs").fetchall()
    assert rows == [("产品参数.md", "ready", 1)]

    collection = chromadb.PersistentClient(path=str(chroma_dir)).get_or_create_collection("knowledge_base")
    assert collection.count() == 1
