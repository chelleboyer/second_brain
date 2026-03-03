"""Capture pipeline — collect → classify → extract entities → resolve novelty → embed → store → suggest."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import structlog

from src.classification.classifier import Classifier
from src.core.entity_resolution import EntityRepository, EntityResolver
from src.core.exceptions import ClassificationError, StorageError
from src.core.suggestions import SuggestionEngine
from src.models.brain_entry import BrainEntry, EntryRelationship
from src.models.enums import EntryType, NoveltyVerdict, PARACategory, RelationshipType
from src.models.strategy import InitiativeLink
from src.retrieval.vector_store import VectorStore
from src.slack.collector import SlackCollector
from src.storage.repository import BrainEntryRepository
from src.storage.strategy_repository import StrategyRepository

if TYPE_CHECKING:
    from uuid import UUID

log = structlog.get_logger(__name__)

# Similarity threshold for content-level duplicate detection (0-1)
DUPLICATE_SIMILARITY_THRESHOLD = 0.92


class CapturePipeline:
    """End-to-end pipeline: collect → classify → extract entities → resolve → embed → store → suggest."""

    def __init__(
        self,
        classifier: Classifier,
        repository: BrainEntryRepository,
        vector_store: VectorStore,
        collector: SlackCollector,
        entity_resolver: EntityResolver | None = None,
        entity_repo: EntityRepository | None = None,
        suggestion_engine: SuggestionEngine | None = None,
        strategy_repo: StrategyRepository | None = None,
    ) -> None:
        self.classifier = classifier
        self.repository = repository
        self.vector_store = vector_store
        self.collector = collector
        self.entity_resolver = entity_resolver
        self.entity_repo = entity_repo
        self.suggestion_engine = suggestion_engine
        self.strategy_repo = strategy_repo

    async def process_messages(
        self, messages: list[dict]
    ) -> tuple[int, int]:
        """Process a batch of Slack messages through the pipeline.

        Returns (processed_count, failed_count).
        """
        processed = 0
        failed = 0
        total = len(messages)

        for i, msg in enumerate(messages, 1):
            ts = msg.get("ts", "")
            log.info("processing_message", progress=f"{i}/{total}", ts=ts)

            try:
                # Dedup check
                if ts and await self.repository.entry_exists(ts):
                    log.info("duplicate_skipped", ts=ts)
                    continue

                # Classify + embed
                text = msg.get("text", "")
                extraction, embedding = await self.classifier.classify_and_embed(
                    text
                )

                entry = await self._build_and_store_entry(
                    text=text,
                    extraction=extraction,
                    embedding=embedding,
                    source="slack",
                    author_id=msg.get("user", "unknown"),
                    author_name=msg.get("user_name", "Unknown"),
                    slack_ts=ts or None,
                    slack_permalink=msg.get("permalink") or None,
                    thread_ts=msg.get("thread_ts"),
                    reply_count=msg.get("reply_count", 0),
                )

                processed += 1
                log.info(
                    "message_processed",
                    entry_id=str(entry.id),
                    type=entry.type.value,
                    para_category=entry.para_category.value,
                    novelty=entry.novelty.value,
                    title=entry.title,
                )

            except (ClassificationError, StorageError) as e:
                failed += 1
                log.error(
                    "message_processing_failed",
                    ts=ts,
                    error=str(e),
                )
            except Exception as e:
                failed += 1
                log.error(
                    "message_processing_unexpected_error",
                    ts=ts,
                    error=str(e),
                    exc_info=True,
                )

        log.info(
            "batch_complete",
            processed=processed,
            failed=failed,
            total=total,
        )
        return processed, failed

    async def catch_up(self) -> tuple[int, int]:
        """Collect new Slack messages and process them.

        Returns (processed_count, failed_count).
        """
        log.info("catch_up_started")
        messages = await self.collector.collect_new_messages()

        if not messages:
            log.info("catch_up_no_messages")
            return 0, 0

        return await self.process_messages(messages)

    async def capture_manual(
        self, text: str, author_name: str = "Michelle"
    ) -> BrainEntry:
        """Capture a manual entry from the dashboard (no Slack origin).

        Classifies, embeds, resolves entities, checks for duplicates, and stores
        with source='manual'.
        """
        log.info("manual_capture_started", text_length=len(text))

        extraction, embedding = await self.classifier.classify_and_embed(text)

        # Check for content-level duplicate before storing
        duplicate = await self._check_content_duplicate(text, embedding)
        if duplicate:
            log.info(
                "manual_capture_duplicate_detected",
                duplicate_of=str(duplicate.id),
                title=duplicate.title,
            )
            # Mark the duplicate and return it so the UI can show the duplicate verdict
            duplicate.novelty = NoveltyVerdict.DUPLICATE
            return duplicate

        entry = await self._build_and_store_entry(
            text=text,
            extraction=extraction,
            embedding=embedding,
            source="manual",
            author_id="manual",
            author_name=author_name,
        )

        log.info(
            "manual_capture_complete",
            entry_id=str(entry.id),
            type=entry.type.value,
            para_category=entry.para_category.value,
            novelty=entry.novelty.value,
            title=entry.title,
        )
        return entry

    # ── Shared pipeline helpers ──────────────────────────────────

    async def _build_and_store_entry(
        self,
        *,
        text: str,
        extraction: dict,
        embedding: list[float],
        source: str,
        author_id: str,
        author_name: str,
        slack_ts: str | None = None,
        slack_permalink: str | None = None,
        thread_ts: str | None = None,
        reply_count: int = 0,
    ) -> BrainEntry:
        """Build, classify, resolve entities, embed, store, and suggest — shared logic."""
        entry_type = extraction.get("type", EntryType.UNCLASSIFIED)
        if isinstance(entry_type, str):
            try:
                entry_type = EntryType(entry_type)
            except ValueError:
                entry_type = EntryType.UNCLASSIFIED

        para_category = extraction.get("para_category", PARACategory.RESOURCE)
        if isinstance(para_category, str):
            try:
                para_category = PARACategory(para_category)
            except ValueError:
                para_category = PARACategory.RESOURCE

        tags = [entry_type.value]
        keywords = extraction.get("keywords", [])
        if keywords:
            tags.extend(keywords)

        entry = BrainEntry(
            type=entry_type,
            title=extraction.get("title", text[:60]),
            summary=extraction.get("summary", text[:200]),
            raw_content=text,
            project=extraction.get("project"),
            tags=tags,
            slack_ts=slack_ts,
            slack_permalink=slack_permalink,
            author_id=author_id,
            author_name=author_name,
            thread_ts=thread_ts,
            reply_count=reply_count,
            source=source,
            para_category=para_category,
            confidence=extraction.get("confidence", 0.0),
            extracted_entities=[
                e.get("name", "") for e in extraction.get("entities", [])
            ],
        )

        # Store in SQLite
        await self.repository.save(entry)

        # Entity resolution (if available)
        resolved = await self._resolve_entities(entry, extraction)

        # Auto-link to matching initiatives (if strategy repo available)
        await self._auto_link_initiatives(entry)

        # Store embedding in Qdrant (if available)
        if embedding:
            await self.vector_store.upsert(
                id=str(entry.id),
                vector=embedding,
                payload={
                    "entry_type": entry.type.value,
                    "para_category": entry.para_category.value,
                    "created_at": entry.created_at.isoformat(),
                },
            )
            entry.embedding_vector_id = str(entry.id)

        # Generate smart suggestions (non-blocking)
        if self.suggestion_engine:
            try:
                suggestions = await self.suggestion_engine.generate_suggestions(
                    entry, resolved
                )
                if suggestions:
                    log.info(
                        "suggestions_generated",
                        entry_id=str(entry.id),
                        count=len(suggestions),
                    )
            except Exception as e:
                log.warning(
                    "suggestion_generation_failed",
                    entry_id=str(entry.id),
                    error=str(e),
                )

        return entry

    async def _resolve_entities(
        self, entry: BrainEntry, extraction: dict
    ) -> list:
        """Run entity resolution and novelty assessment on an entry."""
        resolved = []
        if self.entity_resolver and extraction.get("entities"):
            try:
                resolved = await self.entity_resolver.resolve_entities(
                    extraction["entities"], entry.id
                )
                novelty, augments_id = await self.entity_resolver.assess_novelty(
                    resolved, entry.id
                )
                if novelty != NoveltyVerdict.NEW:
                    entry.novelty = novelty
                    entry.augments_entry_id = augments_id
                    await self.repository.update_novelty(
                        entry.id, novelty, augments_id
                    )
                    # Auto-create EVOLVES relationship
                    if augments_id and self.entity_repo:
                        rel = EntryRelationship(
                            source_entry_id=entry.id,
                            target_entry_id=augments_id,
                            relationship_type=RelationshipType.EVOLVES,
                            confidence=entry.confidence,
                            reason=f"Shares entities: {', '.join(e.name for e in resolved)}",
                        )
                        await self.entity_repo.save_relationship(rel)
            except Exception as e:
                log.warning(
                    "entity_resolution_failed",
                    entry_id=str(entry.id),
                    error=str(e),
                )
        return resolved

    async def _check_content_duplicate(
        self,
        text: str,
        embedding: list[float],
    ) -> BrainEntry | None:
        """Check if content is a near-duplicate of an existing entry.

        Uses two strategies:
        1. Content hash — exact match on normalized text
        2. Vector similarity — near-identical embedding (>= DUPLICATE_SIMILARITY_THRESHOLD)

        Returns the existing entry if duplicate, None otherwise.
        """
        # Strategy 1: exact content hash
        content_hash = hashlib.sha256(text.strip().lower().encode()).hexdigest()
        existing = await self.repository.find_by_content_hash(content_hash)
        if existing:
            return existing

        # Strategy 2: vector similarity (near-duplicates)
        if embedding:
            try:
                from src.retrieval.vector_store import VectorStore
                results = await self.vector_store.search(
                    embedding, limit=3
                )
                for entry_id_str, score in results:
                    if score >= DUPLICATE_SIMILARITY_THRESHOLD:
                        from uuid import UUID
                        dup = await self.repository.get_by_id(UUID(entry_id_str))
                        if dup:
                            log.info(
                                "near_duplicate_detected",
                                score=score,
                                existing_title=dup.title,
                            )
                            return dup
            except Exception as e:
                log.debug("duplicate_vector_check_failed", error=str(e))

        return None

    async def _auto_link_initiatives(
        self, entry: BrainEntry
    ) -> list[InitiativeLink]:
        """Auto-link an entry to matching initiatives by project name and extracted entities.

        Searches for initiatives whose title matches the entry's project field
        or any project-type extracted entity. Creates InitiativeLinks for each
        match (skipping duplicates).

        Returns the list of newly created links.
        """
        if not self.strategy_repo:
            return []

        created_links: list[InitiativeLink] = []

        # Collect candidate project names to match against initiatives
        candidates: list[str] = []
        if entry.project:
            candidates.append(entry.project)
        for entity_name in entry.extracted_entities:
            if entity_name and entity_name not in candidates:
                candidates.append(entity_name)

        if not candidates:
            return []

        seen_initiative_ids: set[str] = set()

        for candidate in candidates:
            matches = await self.strategy_repo.find_initiatives_by_title(candidate)
            for initiative in matches:
                init_id_str = str(initiative.id)
                if init_id_str in seen_initiative_ids:
                    continue
                seen_initiative_ids.add(init_id_str)

                # Skip if link already exists
                if await self.strategy_repo.link_exists(
                    initiative.id, str(entry.id)
                ):
                    continue

                link = InitiativeLink(
                    initiative_id=initiative.id,
                    linked_type="entry",
                    linked_id=str(entry.id),
                    linked_title=entry.title,
                    link_note=f"Auto-linked via project '{candidate}'",
                )
                await self.strategy_repo.save_initiative_link(link)
                created_links.append(link)
                log.info(
                    "initiative_auto_linked",
                    entry_id=str(entry.id),
                    initiative_id=init_id_str,
                    initiative_title=initiative.title,
                    matched_on=candidate,
                )

        return created_links
