"""Progressive summarization — per-entity rollups and cross-entity strategic summaries."""

import json
from datetime import datetime, timezone
from uuid import UUID

import structlog

from src.core.entity_resolution import EntityRepository
from src.models.brain_entry import BrainEntry, Entity, EntitySummary
from src.storage.database import Database
from src.storage.repository import BrainEntryRepository

log = structlog.get_logger(__name__)

# Prompt templates for summarization
ENTITY_SUMMARY_PROMPT = """You are a knowledge synthesizer for a personal second brain system.

Given the following brain entries about the entity "{entity_name}" ({entity_type}), create a concise distilled brief.

The brief should:
1. Capture the key themes and evolution of thinking about this entity
2. Highlight any decisions, risks, or action items
3. Note connections to other entities or projects
4. Be 3-5 sentences maximum

Entries (newest first):
{entries_text}

Respond with ONLY the summary text, no formatting or labels."""

INCREMENTAL_SUMMARY_PROMPT = """You are a knowledge synthesizer for a personal second brain system.

Here is the existing summary for "{entity_name}" ({entity_type}):
---
{existing_summary}
---

New entries have been added since this summary was created. Update the summary to incorporate the new information.

New entries:
{new_entries_text}

Rules:
1. Preserve key insights from the existing summary
2. Integrate new information naturally
3. Keep it 3-5 sentences maximum
4. Note any evolution in thinking or new decisions

Respond with ONLY the updated summary text, no formatting or labels."""

CROSS_ENTITY_SUMMARY_PROMPT = """You are a strategic knowledge synthesizer for a personal second brain system.

Create a strategic synthesis across the following entities and their summaries. Focus on connections, patterns, and strategic implications.

{entity_summaries}

Rules:
1. Identify cross-cutting themes and connections
2. Surface strategic insights that emerge from combining these perspectives
3. Note any tensions or contradictions between entities
4. Be concise but comprehensive (5-8 sentences)

Respond with ONLY the synthesis text, no formatting or labels."""


class SummarizationService:
    """Progressive summarization engine for entities and cross-entity synthesis.

    Supports:
    - Layer 3: Per-entity rollup — synthesize all entries about an entity
    - Layer 4: Cross-entity strategic summary on demand
    - Incremental: only re-summarize when new entries are added

    Requires an LLM provider for generating summaries.
    """

    def __init__(
        self,
        entity_repo: EntityRepository,
        entry_repo: BrainEntryRepository,
        db: Database,
        provider: "LLMProvider | None" = None,
    ) -> None:
        self.entity_repo = entity_repo
        self.entry_repo = entry_repo
        self.db = db
        self.provider = provider

    # ── Entity Summary CRUD ──────────────────────────────────────

    async def get_entity_summary(self, entity_id: UUID) -> EntitySummary | None:
        """Retrieve the current summary for an entity."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM entity_summaries WHERE entity_id = ?",
                (str(entity_id),),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return EntitySummary(
                id=UUID(row["id"]),
                entity_id=UUID(row["entity_id"]),
                summary_text=row["summary_text"],
                entry_count_at_summary=row["entry_count_at_summary"],
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    async def save_entity_summary(self, summary: EntitySummary) -> EntitySummary:
        """Insert or update an entity summary."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO entity_summaries (
                    id, entity_id, summary_text, entry_count_at_summary,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(entity_id) DO UPDATE SET
                    summary_text = excluded.summary_text,
                    entry_count_at_summary = excluded.entry_count_at_summary,
                    updated_at = excluded.updated_at
                """,
                (
                    str(summary.id),
                    str(summary.entity_id),
                    summary.summary_text,
                    summary.entry_count_at_summary,
                    summary.created_at.isoformat(),
                    summary.updated_at.isoformat(),
                ),
            )
            await conn.commit()
        return summary

    # ── Staleness Detection ──────────────────────────────────────

    async def is_summary_stale(self, entity_id: UUID) -> bool:
        """Check if an entity's summary needs to be refreshed.

        A summary is stale when the entity's entry_count exceeds the
        entry_count_at_summary stored in the summary.
        """
        entity = await self.entity_repo.get_entity_by_id(entity_id)
        if not entity:
            return False

        summary = await self.get_entity_summary(entity_id)
        if not summary:
            return entity.entry_count > 0  # No summary yet but entries exist

        return entity.entry_count > summary.entry_count_at_summary

    # ── Per-Entity Summarization (Layer 3) ───────────────────────

    async def summarize_entity(
        self, entity_id: UUID, force: bool = False
    ) -> EntitySummary | None:
        """Generate or update a summary for a specific entity.

        Only regenerates if the summary is stale (new entries added)
        or if force=True.

        Args:
            entity_id: UUID of the entity to summarize
            force: If True, regenerate even if summary is current

        Returns:
            EntitySummary or None if entity doesn't exist or no provider
        """
        if not self.provider:
            log.warning("summarization_skipped_no_provider")
            return None

        entity = await self.entity_repo.get_entity_by_id(entity_id)
        if not entity:
            log.warning("summarization_entity_not_found", entity_id=str(entity_id))
            return None

        existing_summary = await self.get_entity_summary(entity_id)

        # Skip if not stale (unless forced)
        if not force and existing_summary:
            if existing_summary.entry_count_at_summary >= entity.entry_count:
                log.debug(
                    "summary_current",
                    entity_name=entity.name,
                    entry_count=entity.entry_count,
                )
                return existing_summary

        # Get all entries for this entity
        entry_ids = await self.entity_repo.get_entries_for_entity(entity_id)
        entries: list[BrainEntry] = []
        for entry_id_str in entry_ids:
            entry = await self.entry_repo.get_by_id(UUID(entry_id_str))
            if entry and entry.archived_at is None:
                entries.append(entry)

        if not entries:
            log.debug("no_entries_to_summarize", entity_name=entity.name)
            return existing_summary

        entries.sort(key=lambda e: e.created_at, reverse=True)

        # Decide: full summary or incremental update
        if existing_summary and existing_summary.summary_text and not force:
            summary_text = await self._incremental_summarize(
                entity, existing_summary, entries
            )
        else:
            summary_text = await self._full_summarize(entity, entries)

        if not summary_text:
            return existing_summary

        # Save or update the summary
        now = datetime.now(timezone.utc)
        if existing_summary:
            existing_summary.summary_text = summary_text
            existing_summary.entry_count_at_summary = entity.entry_count
            existing_summary.updated_at = now
            await self.save_entity_summary(existing_summary)
            log.info(
                "entity_summary_updated",
                entity_name=entity.name,
                entry_count=entity.entry_count,
            )
            return existing_summary
        else:
            new_summary = EntitySummary(
                entity_id=entity_id,
                summary_text=summary_text,
                entry_count_at_summary=entity.entry_count,
            )
            await self.save_entity_summary(new_summary)
            log.info(
                "entity_summary_created",
                entity_name=entity.name,
                entry_count=entity.entry_count,
            )
            return new_summary

    async def _full_summarize(
        self, entity: Entity, entries: list[BrainEntry]
    ) -> str | None:
        """Generate a full summary from all entries."""
        entries_text = self._format_entries_for_prompt(entries)
        prompt = ENTITY_SUMMARY_PROMPT.format(
            entity_name=entity.name,
            entity_type=entity.entity_type.value,
            entries_text=entries_text,
        )

        try:
            result = await self.provider.classify_and_extract(prompt)
            # The provider returns a dict; we just want the raw text response.
            # Use the summary field or fall back to title.
            return result.get("summary", result.get("title", ""))
        except Exception as e:
            log.error(
                "full_summarization_failed",
                entity_name=entity.name,
                error=str(e),
            )
            return None

    async def _incremental_summarize(
        self,
        entity: Entity,
        existing: EntitySummary,
        all_entries: list[BrainEntry],
    ) -> str | None:
        """Incrementally update a summary with new entries only."""
        # Only include entries newer than the summary's last update
        new_entries = [
            e
            for e in all_entries
            if e.created_at > existing.updated_at
        ]

        if not new_entries:
            return existing.summary_text

        new_entries_text = self._format_entries_for_prompt(new_entries)
        prompt = INCREMENTAL_SUMMARY_PROMPT.format(
            entity_name=entity.name,
            entity_type=entity.entity_type.value,
            existing_summary=existing.summary_text,
            new_entries_text=new_entries_text,
        )

        try:
            result = await self.provider.classify_and_extract(prompt)
            return result.get("summary", result.get("title", ""))
        except Exception as e:
            log.error(
                "incremental_summarization_failed",
                entity_name=entity.name,
                error=str(e),
            )
            return None

    # ── Cross-Entity Strategic Summary (Layer 4) ─────────────────

    async def strategic_summary(
        self, entity_ids: list[UUID] | None = None
    ) -> str | None:
        """Generate a cross-entity strategic synthesis.

        If entity_ids is None, summarizes all entities with existing summaries.

        Args:
            entity_ids: Optional list of specific entity UUIDs to synthesize

        Returns:
            Strategic summary text or None if generation fails
        """
        if not self.provider:
            log.warning("strategic_summary_skipped_no_provider")
            return None

        # Gather entity summaries
        if entity_ids:
            entities_and_summaries: list[tuple[Entity, EntitySummary]] = []
            for eid in entity_ids:
                entity = await self.entity_repo.get_entity_by_id(eid)
                summary = await self.get_entity_summary(eid)
                if entity and summary and summary.summary_text:
                    entities_and_summaries.append((entity, summary))
        else:
            all_entities = await self.entity_repo.get_all_entities()
            entities_and_summaries = []
            for entity in all_entities:
                summary = await self.get_entity_summary(entity.id)
                if summary and summary.summary_text:
                    entities_and_summaries.append((entity, summary))

        if not entities_and_summaries:
            log.info("no_entity_summaries_for_strategic_summary")
            return None

        # Format for prompt
        entity_summaries_text = "\n\n".join(
            f"### {entity.name} ({entity.entity_type.value})\n{summary.summary_text}"
            for entity, summary in entities_and_summaries
        )

        prompt = CROSS_ENTITY_SUMMARY_PROMPT.format(
            entity_summaries=entity_summaries_text
        )

        try:
            result = await self.provider.classify_and_extract(prompt)
            summary_text = result.get("summary", result.get("title", ""))
            log.info(
                "strategic_summary_generated",
                entity_count=len(entities_and_summaries),
            )
            return summary_text
        except Exception as e:
            log.error("strategic_summary_failed", error=str(e))
            return None

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _format_entries_for_prompt(entries: list[BrainEntry], max_entries: int = 20) -> str:
        """Format entries for inclusion in a summarization prompt."""
        lines: list[str] = []
        for entry in entries[:max_entries]:
            date_str = entry.created_at.strftime("%Y-%m-%d")
            lines.append(
                f"- [{date_str}] ({entry.type.value}) {entry.title}: {entry.summary}"
            )
        if len(entries) > max_entries:
            lines.append(f"... and {len(entries) - max_entries} more entries")
        return "\n".join(lines)
