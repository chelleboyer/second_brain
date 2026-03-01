"""SQLite database setup and schema initialization."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import aiosqlite
import structlog

log = structlog.get_logger(__name__)


class Database:
    """SQLite database manager with schema initialization."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._is_memory = self.db_path == ":memory:"
        self._persistent_conn: aiosqlite.Connection | None = None

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Async context manager for database connections.

        For in-memory databases, reuses a single persistent connection
        since each new connection creates a separate empty database.
        For file-based databases, creates a new connection each time.
        """
        if self._is_memory:
            if self._persistent_conn is None:
                self._persistent_conn = await aiosqlite.connect(self.db_path)
                self._persistent_conn.row_factory = aiosqlite.Row
            yield self._persistent_conn
        else:
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row
            try:
                yield conn
            finally:
                await conn.close()

    async def close(self) -> None:
        """Close the persistent connection (for in-memory databases)."""
        if self._persistent_conn is not None:
            await self._persistent_conn.close()
            self._persistent_conn = None

    async def init_db(self) -> None:
        """Create tables, FTS5 virtual table, and sync triggers."""
        log.info("initializing_database", db_path=str(self.db_path))

        async with self.get_connection() as conn:
            # Main entries table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS brain_entries (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    raw_content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    project TEXT,
                    tags TEXT NOT NULL DEFAULT '[]',
                    embedding_vector_id TEXT,
                    slack_ts TEXT UNIQUE,
                    slack_permalink TEXT,
                    author_id TEXT NOT NULL,
                    author_name TEXT NOT NULL,
                    thread_ts TEXT,
                    reply_count INTEGER NOT NULL DEFAULT 0,
                    archived_at TEXT,
                    source TEXT NOT NULL DEFAULT 'slack'
                )
            """)

            # App state table for tracking last processed timestamp
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS app_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)

            # FTS5 virtual table (content-sync with brain_entries)
            await conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS brain_entries_fts
                USING fts5(
                    title, summary, raw_content, tags,
                    content='brain_entries',
                    content_rowid='rowid'
                )
            """)

            # Sync triggers: keep FTS5 in sync with brain_entries
            # AFTER INSERT trigger
            await conn.execute("""
                CREATE TRIGGER IF NOT EXISTS brain_entries_ai
                AFTER INSERT ON brain_entries BEGIN
                    INSERT INTO brain_entries_fts(
                        rowid, title, summary, raw_content, tags
                    ) VALUES (
                        new.rowid, new.title, new.summary,
                        new.raw_content, new.tags
                    );
                END
            """)

            # AFTER DELETE trigger
            await conn.execute("""
                CREATE TRIGGER IF NOT EXISTS brain_entries_ad
                AFTER DELETE ON brain_entries BEGIN
                    INSERT INTO brain_entries_fts(
                        brain_entries_fts, rowid, title, summary,
                        raw_content, tags
                    ) VALUES (
                        'delete', old.rowid, old.title, old.summary,
                        old.raw_content, old.tags
                    );
                END
            """)

            # AFTER UPDATE trigger
            await conn.execute("""
                CREATE TRIGGER IF NOT EXISTS brain_entries_au
                AFTER UPDATE ON brain_entries BEGIN
                    INSERT INTO brain_entries_fts(
                        brain_entries_fts, rowid, title, summary,
                        raw_content, tags
                    ) VALUES (
                        'delete', old.rowid, old.title, old.summary,
                        old.raw_content, old.tags
                    );
                    INSERT INTO brain_entries_fts(
                        rowid, title, summary, raw_content, tags
                    ) VALUES (
                        new.rowid, new.title, new.summary,
                        new.raw_content, new.tags
                    );
                END
            """)

            await conn.commit()
            log.info("database_initialized")
