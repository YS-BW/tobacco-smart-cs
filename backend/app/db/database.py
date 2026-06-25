"""SQLite 数据库连接管理。"""

import aiosqlite

from app.config import SQLITE_DB_PATH, BASE_DIR

# 建表 SQL 路径
INIT_SQL_PATH = BASE_DIR / "app" / "db" / "init.sql"


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接。"""
    db = await aiosqlite.connect(SQLITE_DB_PATH)
    db.row_factory = aiosqlite.Row
    # 启用外键约束
    await db.execute("PRAGMA foreign_keys = ON")
    return db


async def init_db() -> None:
    """启动时执行建表脚本。"""
    sql = INIT_SQL_PATH.read_text(encoding="utf-8")
    db = await get_db()
    try:
        await db.executescript(sql)
        await db.commit()
    finally:
        await db.close()
