"""SQLite 数据库连接管理。"""

import asyncio

import aiosqlite

from app.config import SQLITE_DB_PATH, BASE_DIR

# 建表 SQL 路径
INIT_SQL_PATH = BASE_DIR / "app" / "db" / "init.sql"

# 序列化并发写操作，避免 database is locked
_db_write_lock = asyncio.Lock()


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接。"""
    db = await aiosqlite.connect(SQLITE_DB_PATH, timeout=30)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode = WAL")
    await db.execute("PRAGMA busy_timeout = 10000")
    return db


def get_write_lock() -> asyncio.Lock:
    """获取数据库写锁，用于序列化并发写操作。"""
    return _db_write_lock


async def init_db() -> None:
    """启动时执行建表脚本。"""
    sql = INIT_SQL_PATH.read_text(encoding="utf-8")
    db = await get_db()
    try:
        await db.executescript(sql)
        await db.commit()
    finally:
        await db.close()
