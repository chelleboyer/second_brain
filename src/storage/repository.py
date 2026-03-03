"""Brain entry repository — CRUD operations via explicit SQL."""

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

import structlog

from src.models.brain_entry import BrainEntry
from src.models.enums import EntryType, NoveltyVerdict, PARACategory
from src.storage.database import Database

log = structlog.get_logger(__name__)


class BrainEntryRepository:
    """Repository for BrainEntry persistence in SQLite."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def save(self, entry: BrainEntry) -> BrainEntry:
        """Save a brain entry. Skips silently if slack_ts already exists."""
        content_hash = hashlib.sha256(
            entry.raw_content.strip().lower().encode()
        ).hexdigest()
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO brain_entries (
                    id, type, title, summary, raw_content, created_at,
                    project, tags, embedding_vector_id, slack_ts,
                    slack_permalink, author_id, author_name, thread_ts,
                    reply_count, archived_at, source,
                    para_category, confidence, extracted_entities,
                    novelty, augments_entry_id, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(entry.id),
                    entry.type.value,
                    entry.title,
                    entry.summary,
                    entry.raw_content,
                    entry.created_at.isoformat(),
                    entry.project,
                    json.dumps(entry.tags),
                    entry.embedding_vector_id,
                    entry.slack_ts,
                    entry.slack_permalink,
                    entry.author_id,
                    entry.author_name,
                    entry.thread_ts,
                    entry.reply_count,
                    entry.archived_at.isoformat() if entry.archived_at else None,
                    entry.source,
                    entry.para_category.value,
                    entry.confidence,
                    json.dumps(entry.extracted_entities),
                    entry.novelty.value,
                    str(entry.augments_entry_id) if entry.augments_entry_id else None,
                    content_hash,
                ),
            )
            await conn.commit()
            log.info("entry_saved", entry_id=str(entry.id), type=entry.type.value)
        return entry

    async def get_by_id(self, entry_id: UUID) -> BrainEntry | None:
        """Retrieve a brain entry by ID."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM brain_entries WHERE id = ?", (str(entry_id),)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_entry(row)

    async def get_by_type(self, entry_type: EntryType, include_archived: bool = False) -> list[BrainEntry]:
        """Get all entries of a specific type."""
        if include_archived:
            query = "SELECT * FROM brain_entries WHERE type = ? ORDER BY created_at DESC"
        else:
            query = "SELECT * FROM brain_entries WHERE type = ? AND archived_at IS NULL ORDER BY created_at DESC"
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, (entry_type.value,))
            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    async def search_keyword(
        self, query: str, limit: int = 20
    ) -> list[tuple[BrainEntry, float]]:
        """Full-text search using FTS5 with BM25 ranking."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT brain_entries.*, bm25(brain_entries_fts) as rank
                FROM brain_entries_fts
                JOIN brain_entries ON brain_entries.rowid = brain_entries_fts.rowid
                WHERE brain_entries_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (query, limit),
            )
            rows = await cursor.fetchall()
            results: list[tuple[BrainEntry, float]] = []
            for row in rows:
                entry = self._row_to_entry(row)
                rank = row["rank"]
                results.append((entry, rank))
            return results

    async def get_digest(self, date: str) -> dict[str, int]:
        """Get count of entries by type for a given date (YYYY-MM-DD)."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT type, COUNT(*) as count
                FROM brain_entries
                WHERE date(created_at) = ?
                GROUP BY type
                """,
                (date,),
            )
            rows = await cursor.fetchall()
            return {row["type"]: row["count"] for row in rows}

    async def get_last_processed_ts(self) -> str | None:
        """Get the last processed Slack timestamp."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT value FROM app_state WHERE key = 'last_processed_ts'"
            )
            row = await cursor.fetchone()
            return row["value"] if row else None

    async def set_last_processed_ts(self, ts: str) -> None:
        """Set the last processed Slack timestamp."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO app_state (key, value) VALUES ('last_processed_ts', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (ts,),
            )
            await conn.commit()

    async def entry_exists(self, slack_ts: str) -> bool:
        """Check if an entry with this slack_ts already exists."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM brain_entries WHERE slack_ts = ?", (slack_ts,)
            )
            return await cursor.fetchone() is not None

    async def archive(self, entry_id: UUID) -> BrainEntry | None:
        """Soft-archive an entry by setting archived_at."""
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE brain_entries SET archived_at = ? WHERE id = ?",
                (now, str(entry_id)),
            )
            await conn.commit()
            log.info("entry_archived", entry_id=str(entry_id))
        return await self.get_by_id(entry_id)

    async def unarchive(self, entry_id: UUID) -> BrainEntry | None:
        """Restore an archived entry by clearing archived_at."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE brain_entries SET archived_at = NULL WHERE id = ?",
                (str(entry_id),),
            )
            await conn.commit()
            log.info("entry_unarchived", entry_id=str(entry_id))
        return await self.get_by_id(entry_id)

    async def pin(self, entry_id: UUID) -> BrainEntry | None:
        """Pin an entry by setting pinned_at."""
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE brain_entries SET pinned_at = ? WHERE id = ?",
                (now, str(entry_id)),
            )
            await conn.commit()
            log.info("entry_pinned", entry_id=str(entry_id))
        return await self.get_by_id(entry_id)

    async def unpin(self, entry_id: UUID) -> BrainEntry | None:
        """Unpin an entry by clearing pinned_at."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE brain_entries SET pinned_at = NULL WHERE id = ?",
                (str(entry_id),),
            )
            await conn.commit()
            log.info("entry_unpinned", entry_id=str(entry_id))
        return await self.get_by_id(entry_id)

    async def get_pinned(self, limit: int = 50) -> list[BrainEntry]:
        """Get pinned entries, newest pin first."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM brain_entries WHERE pinned_at IS NOT NULL AND archived_at IS NULL ORDER BY pinned_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    async def delete(self, entry_id: UUID) -> bool:
        """Permanently delete an entry. Returns True if deleted."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM brain_entries WHERE id = ?", (str(entry_id),)
            )
            await conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                log.info("entry_deleted", entry_id=str(entry_id))
            return deleted

    async def update(
        self,
        entry_id: UUID,
        *,
        title: str | None = None,
        summary: str | None = None,
        entry_type: EntryType | None = None,
        project: str | None = None,
        tags: list[str] | None = None,
    ) -> BrainEntry | None:
        """Update editable fields on an entry. Only non-None fields are changed."""
        fields: list[str] = []
        values: list = []
        if title is not None:
            fields.append("title = ?")
            values.append(title)
        if summary is not None:
            fields.append("summary = ?")
            values.append(summary)
        if entry_type is not None:
            fields.append("type = ?")
            values.append(entry_type.value)
        if project is not None:
            fields.append("project = ?")
            values.append(project if project else None)
        if tags is not None:
            fields.append("tags = ?")
            values.append(json.dumps(tags))
        if not fields:
            return await self.get_by_id(entry_id)
        values.append(str(entry_id))
        async with self.db.get_connection() as conn:
            await conn.execute(
                f"UPDATE brain_entries SET {', '.join(fields)} WHERE id = ?",
                tuple(values),
            )
            await conn.commit()
            log.info("entry_updated", entry_id=str(entry_id), fields=[f.split(" =")[0] for f in fields])
        return await self.get_by_id(entry_id)

    async def get_recent(
        self, limit: int = 50, include_archived: bool = False
    ) -> list[BrainEntry]:
        """Get most recent entries, newest first."""
        if include_archived:
            query = "SELECT * FROM brain_entries ORDER BY created_at DESC LIMIT ?"
            params: tuple = (limit,)
        else:
            query = "SELECT * FROM brain_entries WHERE archived_at IS NULL ORDER BY created_at DESC LIMIT ?"
            params = (limit,)
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    async def get_archived(self, limit: int = 100) -> list[BrainEntry]:
        """Get archived entries, newest first."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM brain_entries WHERE archived_at IS NOT NULL ORDER BY archived_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    async def count_all(self) -> dict[str, int]:
        """Get total entry counts: active, archived, total."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute("SELECT COUNT(*) as total FROM brain_entries")
            row = await cursor.fetchone()
            total = row["total"] if row else 0
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM brain_entries WHERE archived_at IS NOT NULL"
            )
            row = await cursor.fetchone()
            archived = row["cnt"] if row else 0
            return {"total": total, "archived": archived, "active": total - archived}

    async def get_type_breakdown(self) -> dict[str, int]:
        """Get active (non-archived) entry count per type."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT type, COUNT(*) as count
                FROM brain_entries
                WHERE archived_at IS NULL
                GROUP BY type
                ORDER BY count DESC
                """
            )
            rows = await cursor.fetchall()
            return {row["type"]: row["count"] for row in rows}

    async def get_activity_by_day(self, days: int = 7) -> list[dict]:
        """Get entry counts per day for the last N days (including zeros)."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT date(created_at) as day, COUNT(*) as count
                FROM brain_entries
                WHERE created_at >= date('now', ?)
                GROUP BY date(created_at)
                ORDER BY day ASC
                """,
                (f"-{days} days",),
            )
            rows = await cursor.fetchall()
            return [{"day": row["day"], "count": row["count"]} for row in rows]

    async def update_novelty(
        self, entry_id: UUID, novelty: NoveltyVerdict, augments_id: UUID | None
    ) -> None:
        """Update the novelty verdict and augments link for an entry."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                "UPDATE brain_entries SET novelty = ?, augments_entry_id = ? WHERE id = ?",
                (
                    novelty.value,
                    str(augments_id) if augments_id else None,
                    str(entry_id),
                ),
            )
            await conn.commit()

    async def get_entries_in_date_range(
        self, start_date: str, end_date: str, include_archived: bool = False,
    ) -> list[BrainEntry]:
        """Get entries created between start_date and end_date (inclusive, YYYY-MM-DD)."""
        archived_clause = "" if include_archived else "AND archived_at IS NULL"
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                f"""
                SELECT * FROM brain_entries
                WHERE date(created_at) >= ? AND date(created_at) <= ?
                {archived_clause}
                ORDER BY created_at DESC
                """,
                (start_date, end_date),
            )
            rows = await cursor.fetchall()
            return [self._row_to_entry(row) for row in rows]

    async def get_project_breakdown(self) -> list[dict]:
        """Get active entry counts grouped by project (non-null only)."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT project, type, COUNT(*) as count
                FROM brain_entries
                WHERE archived_at IS NULL AND project IS NOT NULL AND project != ''
                GROUP BY project, type
                ORDER BY project, count DESC
                """
            )
            rows = await cursor.fetchall()

            from collections import defaultdict
            projects: dict[str, dict] = defaultdict(lambda: {"total": 0, "types": {}})
            for row in rows:
                p = row["project"]
                projects[p]["total"] += row["count"]
                projects[p]["types"][row["type"]] = row["count"]

            return [
                {"project": p, "total": d["total"], "types": d["types"]}
                for p, d in sorted(projects.items(), key=lambda x: x[1]["total"], reverse=True)
            ]

    async def get_para_breakdown(self) -> dict[str, int]:
        """Get active entry counts grouped by PARA category."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT para_category, COUNT(*) as count
                FROM brain_entries
                WHERE archived_at IS NULL
                GROUP BY para_category
                ORDER BY count DESC
                """
            )
            rows = await cursor.fetchall()
            return {row["para_category"]: row["count"] for row in rows}

    async def find_by_content_hash(self, content_hash: str) -> BrainEntry | None:
        """Find an existing entry with the same content hash (exact duplicate check)."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM brain_entries WHERE content_hash = ? LIMIT 1",
                (content_hash,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_entry(row)

    @staticmethod
    def _row_to_entry(row) -> BrainEntry:
        """Convert a database row to a BrainEntry model."""
        # Handle rows that may come from older schema (pre-Phase-1)
        row_keys = row.keys() if hasattr(row, 'keys') else []
        return BrainEntry(
            id=UUID(row["id"]),
            type=EntryType(row["type"]),
            title=row["title"],
            summary=row["summary"],
            raw_content=row["raw_content"],
            created_at=datetime.fromisoformat(row["created_at"]),
            project=row["project"],
            tags=json.loads(row["tags"]),
            embedding_vector_id=row["embedding_vector_id"],
            slack_ts=row["slack_ts"],
            slack_permalink=row["slack_permalink"],
            author_id=row["author_id"],
            author_name=row["author_name"],
            thread_ts=row["thread_ts"],
            reply_count=row["reply_count"],
            archived_at=(
                datetime.fromisoformat(row["archived_at"])
                if row["archived_at"]
                else None
            ),
            source=row["source"],
            para_category=PARACategory(row["para_category"]) if "para_category" in row_keys else PARACategory.RESOURCE,
            confidence=row["confidence"] if "confidence" in row_keys else 0.0,
            extracted_entities=json.loads(row["extracted_entities"]) if "extracted_entities" in row_keys else [],
            novelty=NoveltyVerdict(row["novelty"]) if "novelty" in row_keys else NoveltyVerdict.NEW,
            augments_entry_id=UUID(row["augments_entry_id"]) if "augments_entry_id" in row_keys and row["augments_entry_id"] else None,
            pinned_at=(
                datetime.fromisoformat(row["pinned_at"])
                if "pinned_at" in row_keys and row["pinned_at"]
                else None
            ),
        )
