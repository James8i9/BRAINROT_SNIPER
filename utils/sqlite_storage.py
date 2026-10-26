"""
utils/sqlite_storage.py
========================
Persistent SQLite-backed FSM storage for aiogram 3.
Uses the same DATABASE_PATH as the rest of the app (Railway volume).
"""

import json
import logging
from typing import Any, Dict, Optional

import aiosqlite
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType

from database.paths import get_db_path

logger = logging.getLogger(__name__)


class SQLiteStorage(BaseStorage):
    """aiogram 3 FSM storage backed by the shared SQLite file."""

    async def set_state(
        self,
        key: StorageKey,
        state: StateType = None,
    ) -> None:
        state_str = state.state if state else None
        async with aiosqlite.connect(get_db_path()) as db:
            await db.execute(
                """
                INSERT INTO fsm_states (chat_id, user_id, bot_id, state)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id, bot_id) DO UPDATE SET
                    state      = excluded.state,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key.chat_id, key.user_id, key.bot_id, state_str),
            )
            await db.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        async with aiosqlite.connect(get_db_path()) as db:
            async with db.execute(
                "SELECT state FROM fsm_states WHERE chat_id=? AND user_id=? AND bot_id=?",
                (key.chat_id, key.user_id, key.bot_id),
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else None

    async def set_data(
        self,
        key: StorageKey,
        data: Dict[str, Any],
    ) -> None:
        async with aiosqlite.connect(get_db_path()) as db:
            await db.execute(
                """
                INSERT INTO fsm_data (chat_id, user_id, bot_id, data)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id, bot_id) DO UPDATE SET
                    data       = excluded.data,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key.chat_id, key.user_id, key.bot_id, json.dumps(data)),
            )
            await db.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        async with aiosqlite.connect(get_db_path()) as db:
            async with db.execute(
                "SELECT data FROM fsm_data WHERE chat_id=? AND user_id=? AND bot_id=?",
                (key.chat_id, key.user_id, key.bot_id),
            ) as cur:
                row = await cur.fetchone()
        if not row or not row[0]:
            return {}
        try:
            return json.loads(row[0])
        except Exception:
            return {}

    async def close(self) -> None:
        pass
