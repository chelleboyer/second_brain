"""Capture pipeline — collect → classify → extract entities → resolve novelty → embed → store → suggest."""

import structlog

from src.classification.classifier import Classifier
from src.core.entity_resolution import EntityRepository, EntityResolver
from src.core.exceptions import ClassificationError, StorageError
from src.core.suggestions import SuggestionEngine
from src.models.brain_entry import BrainEntry, EntryRelationship
from src.models.enums import EntryType, NoveltyVerdict, PARACategory, RelationshipType
from src.retrieval.vector_store import VectorStore
from src.slack.collector import SlackCollector
from src.storage.repository import BrainEntryRepository

log = structlog.get_logger(__name__)


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
    ) -> None:
        self.classifier = classifier
        self.repository = repository
        self.vector_store = vector_store
        self.collector = collector
        self.entity_resolver = entity_resolver
        self.entity_repo = entity_repo
        self.suggestion_engine = suggestion_engine

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

                # Build entry with enhanced classification fields
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

                # Build tags from type + keywords
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
                    slack_ts=ts or None,
                    slack_permalink=msg.get("permalink") or None,
                    author_id=msg.get("user", "unknown"),
                    author_name=msg.get("user_name", "Unknown"),
                    thread_ts=msg.get("thread_ts"),
                    reply_count=msg.get("reply_count", 0),
                    source="slack",
                    para_category=para_category,
                    confidence=extraction.get("confidence", 0.0),
                    extracted_entities=[
                        e.get("name", "") for e in extraction.get("entities", [])
                    ],
                )

                # Store in SQLite
                await self.repository.save(entry)

                # Entity resolution (if available)
                resolved = []
                if self.entity_resolver and extraction.get("entities"):
                    try:
                        resolved = await self.entity_resolver.resolve_entities(
                            extraction["entities"], entry.id
                        )
                        # Assess novelty
                        novelty, augments_id = (
                            await self.entity_resolver.assess_novelty(
                                resolved, entry.id
                            )
                        )
                        if novelty != NoveltyVerdict.NEW:
                            entry.novelty = novelty
                            entry.augments_entry_id = augments_id
                            # Update the entry in DB with novelty info
                            async with self.repository.db.get_connection() as conn:
                                await conn.execute(
                                    "UPDATE brain_entries SET novelty = ?, augments_entry_id = ? WHERE id = ?",
                                    (novelty.value, str(augments_id) if augments_id else None, str(entry.id)),
                                )
                                await conn.commit()

                            # Auto-create relationship if augmenting
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

                # Phase 2: Generate smart suggestions (non-blocking)
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

        Classifies, embeds, resolves entities, and stores with source='manual'.
        """
        log.info("manual_capture_started", text_length=len(text))

        extraction, embedding = await self.classifier.classify_and_embed(text)

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
            slack_ts=None,
            slack_permalink=None,
            author_id="manual",
            author_name=author_name,
            source="manual",
            para_category=para_category,
            confidence=extraction.get("confidence", 0.0),
            extracted_entities=[
                e.get("name", "") for e in extraction.get("entities", [])
            ],
        )

        await self.repository.save(entry)

        # Entity resolution (if available)
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
                    async with self.repository.db.get_connection() as conn:
                        await conn.execute(
                            "UPDATE brain_entries SET novelty = ?, augments_entry_id = ? WHERE id = ?",
                            (novelty.value, str(augments_id) if augments_id else None, str(entry.id)),
                        )
                        await conn.commit()

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

        # Phase 2: Generate smart suggestions (non-blocking)
        suggestions = []
        if self.suggestion_engine:
            try:
                suggestions = await self.suggestion_engine.generate_suggestions(
                    entry, resolved
                )
                if suggestions:
                    log.info(
                        "manual_capture_suggestions",
                        entry_id=str(entry.id),
                        count=len(suggestions),
                    )
            except Exception as e:
                log.warning(
                    "suggestion_generation_failed",
                    entry_id=str(entry.id),
                    error=str(e),
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
