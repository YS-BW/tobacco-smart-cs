"""Background queue for knowledge document processing."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

DocumentProcessor = Callable[[str, int, str, str], Awaitable[int]]


@dataclass(frozen=True)
class DocumentJob:
    file_path: str
    doc_id: int
    filename: str
    file_type: str
    processor: DocumentProcessor


_queue: asyncio.Queue[DocumentJob] | None = None
_worker_tasks: set[asyncio.Task] = set()
_worker_loop: asyncio.AbstractEventLoop | None = None


def start_document_workers(worker_count: int = 1) -> None:
    """Start background workers for document processing."""
    global _queue, _worker_loop

    loop = asyncio.get_running_loop()
    if _queue is None or _worker_loop is not loop:
        _queue = asyncio.Queue()
        _worker_loop = loop
        _worker_tasks.clear()

    _worker_tasks.difference_update(task for task in _worker_tasks if task.done())
    missing = max(0, worker_count - len(_worker_tasks))
    for index in range(missing):
        task = loop.create_task(_process_jobs(), name=f"document-processor-{index + 1}")
        _worker_tasks.add(task)


async def stop_document_workers() -> None:
    """Stop background workers cleanly."""
    global _queue, _worker_loop

    if not _worker_tasks:
        _queue = None
        _worker_loop = None
        return

    for task in _worker_tasks:
        task.cancel()
    await asyncio.gather(*_worker_tasks, return_exceptions=True)
    _worker_tasks.clear()
    _queue = None
    _worker_loop = None


async def enqueue_document(
    file_path: str,
    doc_id: int,
    filename: str,
    file_type: str,
    processor: DocumentProcessor,
) -> None:
    """Queue a document for processing without waiting for processing itself."""
    start_document_workers()
    if _queue is None:
        raise RuntimeError("document processor queue is not available")
    _queue.put_nowait(DocumentJob(file_path, doc_id, filename, file_type, processor))


async def _process_jobs() -> None:
    assert _queue is not None
    while True:
        job = await _queue.get()
        try:
            await job.processor(job.file_path, job.doc_id, job.filename, job.file_type)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("文档后台处理失败: %s", job.filename)
        finally:
            _queue.task_done()
        # markitdown 本地解析为主，无限流；MinerU 仅作兜底，间隔防限流
        await asyncio.sleep(2)
