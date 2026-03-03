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

    async def nuke_all(self) -> dict[str, int]:
        """Delete ALL data from every table. Returns counts per table.

        This is a destructive operation — use with caution.
        Preserves schema and indexes; only deletes rows.
        """
        tables = [
            "initiative_links",
            "entity_mentions",
            "entry_relationships",
            "entity_summaries",
            "influence_deltas",
            "weekly_simulations",
            "strategic_assets",
            "initiatives",
            "stakeholders",
            "entities",
            "brain_entries",
            "app_state",
        ]
        counts: dict[str, int] = {}
        async with self.get_connection() as conn:
            for table in tables:
                try:
                    cursor = await conn.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                    row = await cursor.fetchone()
                    counts[table] = row["cnt"] if row else 0
                    await conn.execute(f"DELETE FROM {table}")
                except Exception:
                    counts[table] = 0
            # Rebuild FTS index
            try:
                await conn.execute(
                    "INSERT INTO brain_entries_fts(brain_entries_fts) VALUES('rebuild')"
                )
            except Exception:
                pass
            await conn.commit()
        log.info("nuke_all_complete", counts=counts)
        return counts

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
                    source TEXT NOT NULL DEFAULT 'slack',
                    para_category TEXT NOT NULL DEFAULT 'resource',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    extracted_entities TEXT NOT NULL DEFAULT '[]',
                    novelty TEXT NOT NULL DEFAULT 'new',
                    augments_entry_id TEXT
                )
            """)

            # Entities table — named things that span multiple captures
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    aliases TEXT NOT NULL DEFAULT '[]',
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    entry_count INTEGER NOT NULL DEFAULT 0,
                    embedding_vector_id TEXT
                )
            """)

            # Index for fast entity lookup by name
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_entities_name
                ON entities(name COLLATE NOCASE)
            """)

            # Entity mentions — junction table linking entities to entries
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS entity_mentions (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    entry_id TEXT NOT NULL,
                    mention_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES entities(id),
                    FOREIGN KEY (entry_id) REFERENCES brain_entries(id)
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity
                ON entity_mentions(entity_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_mentions_entry
                ON entity_mentions(entry_id)
            """)

            # Entry relationships — typed directional links between entries
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS entry_relationships (
                    id TEXT PRIMARY KEY,
                    source_entry_id TEXT NOT NULL,
                    target_entry_id TEXT NOT NULL,
                    relationship_type TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    created_at TEXT NOT NULL,
                    reason TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (source_entry_id) REFERENCES brain_entries(id),
                    FOREIGN KEY (target_entry_id) REFERENCES brain_entries(id)
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_source
                ON entry_relationships(source_entry_id)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_relationships_target
                ON entry_relationships(target_entry_id)
            """)

            # Entity summaries — tracks progressive summarization state
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS entity_summaries (
                    id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL UNIQUE,
                    summary_text TEXT NOT NULL DEFAULT '',
                    entry_count_at_summary INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (entity_id) REFERENCES entities(id)
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_entity_summaries_entity
                ON entity_summaries(entity_id)
            """)

            # ── Phase II: Strategic Positioning tables ───────────

            # Stakeholders — people whose influence dynamics are tracked
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS stakeholders (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT '',
                    influence_level INTEGER NOT NULL DEFAULT 5,
                    incentives TEXT NOT NULL DEFAULT '',
                    alignment_score INTEGER NOT NULL DEFAULT 0,
                    dependency_on_you INTEGER NOT NULL DEFAULT 0,
                    trust_score INTEGER NOT NULL DEFAULT 5,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_stakeholders_name
                ON stakeholders(name COLLATE NOCASE)
            """)

            # Initiatives — projects scored for strategic alignment
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS initiatives (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    initiative_type TEXT NOT NULL DEFAULT 'scored',
                    authority INTEGER NOT NULL DEFAULT 0,
                    asymmetric_info INTEGER NOT NULL DEFAULT 0,
                    future_mobility INTEGER NOT NULL DEFAULT 0,
                    reusable_leverage INTEGER NOT NULL DEFAULT 0,
                    right_visibility INTEGER NOT NULL DEFAULT 0,
                    category TEXT NOT NULL DEFAULT 'maintenance',
                    visibility TEXT NOT NULL DEFAULT 'hidden',
                    risk_level INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    linked_entry_ids TEXT NOT NULL DEFAULT '[]',
                    stakeholder_ids TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_initiatives_category
                ON initiatives(category)
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_initiatives_status
                ON initiatives(status)
            """)

            # Initiative links — connects initiatives to entries/entities
            await conn.execute("""                CREATE TABLE IF NOT EXISTS initiative_links (
                    id TEXT PRIMARY KEY,
                    initiative_id TEXT NOT NULL,
                    linked_type TEXT NOT NULL,
                    linked_id TEXT NOT NULL,
                    linked_title TEXT NOT NULL DEFAULT '',
                    link_note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (initiative_id) REFERENCES initiatives(id) ON DELETE CASCADE
                )
            """)

            # Strategic assets — reputation and optionality assets
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS strategic_assets (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    asset_type TEXT NOT NULL DEFAULT 'reputation',
                    visibility TEXT NOT NULL DEFAULT 'hidden',
                    reusability_score INTEGER NOT NULL DEFAULT 0,
                    signaling_strength INTEGER NOT NULL DEFAULT 0,
                    market_relevance INTEGER NOT NULL DEFAULT 0,
                    compounding_potential INTEGER NOT NULL DEFAULT 0,
                    portability_score INTEGER NOT NULL DEFAULT 0,
                    market_demand INTEGER NOT NULL DEFAULT 0,
                    monetization_potential INTEGER NOT NULL DEFAULT 0,
                    time_to_deploy INTEGER NOT NULL DEFAULT 0,
                    linked_initiative_ids TEXT NOT NULL DEFAULT '[]',
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_strategic_assets_type
                ON strategic_assets(asset_type)
            """)

            # Influence deltas — weekly influence tracking
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS influence_deltas (
                    id TEXT PRIMARY KEY,
                    week_start TEXT NOT NULL,
                    advice_sought INTEGER NOT NULL DEFAULT 0,
                    decision_changed INTEGER NOT NULL DEFAULT 0,
                    framing_adopted INTEGER NOT NULL DEFAULT 0,
                    consultation_count INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    delta_score INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_influence_deltas_week
                ON influence_deltas(week_start)
            """)

            # Weekly simulations — strategic simulation outputs
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS weekly_simulations (
                    id TEXT PRIMARY KEY,
                    week_start TEXT NOT NULL,
                    strategic_move TEXT NOT NULL DEFAULT '',
                    maintenance_tasks TEXT NOT NULL DEFAULT '[]',
                    position_building TEXT NOT NULL DEFAULT '[]',
                    influence_trend TEXT NOT NULL DEFAULT '',
                    optionality_trend TEXT NOT NULL DEFAULT '',
                    top_initiatives TEXT NOT NULL DEFAULT '[]',
                    raw_analysis TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_weekly_simulations_week
                ON weekly_simulations(week_start)
            """)

            # ── Migrations: add columns to existing tables ───────
            # SQLite's CREATE TABLE IF NOT EXISTS won't add new columns
            # to an already-existing table, so we ALTER TABLE instead.
            migration_columns = [
                ("brain_entries", "para_category", "TEXT NOT NULL DEFAULT 'resource'"),
                ("brain_entries", "confidence", "REAL NOT NULL DEFAULT 0.0"),
                ("brain_entries", "extracted_entities", "TEXT NOT NULL DEFAULT '[]'"),
                ("brain_entries", "novelty", "TEXT NOT NULL DEFAULT 'new'"),
                ("brain_entries", "augments_entry_id", "TEXT"),
                ("brain_entries", "content_hash", "TEXT"),
                ("brain_entries", "pinned_at", "TEXT"),
                ("initiatives", "initiative_type", "TEXT NOT NULL DEFAULT 'scored'"),
            ]
            for table, column, col_type in migration_columns:
                try:
                    await conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
                    )
                    log.info("migration_added_column", table=table, column=column)
                except Exception:
                    # Column already exists — safe to ignore
                    pass

            # Post-migration indexes (depend on migrated columns)
            try:
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_initiatives_type
                    ON initiatives(initiative_type)
                """)
            except Exception:
                pass

            try:
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_initiative_links_initiative
                    ON initiative_links(initiative_id)
                """)
            except Exception:
                pass

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
