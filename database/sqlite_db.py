"""
database/sqlite_db.py
=====================
Async SQLite connection helper used by all services.
"""

import aiosqlite
from contextlib import asynccontextmanager

from database.paths import get_db_path


@asynccontextmanager
async def get_db():
    """
    Async context manager yielding an aiosqlite connection.
    Row factory is set so rows behave like dicts.
    """
    async with aiosqlite.connect(get_db_path()) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn
