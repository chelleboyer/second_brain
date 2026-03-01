"""Capture pipeline — collect → classify → embed → store."""

import structlog

from src.classification.classifier import Classifier
from src.core.exceptions import ClassificationError, StorageError
from src.models.brain_entry import BrainEntry
from src.models.enums import EntryType
from src.retrieval.vector_store import VectorStore
from src.slack.collector import SlackCollector
from src.storage.repository import BrainEntryRepository

log = structlog.get_logger(__name__)


class CapturePipeline:
    """End-to-end pipeline: collect → classify → embed → store."""

    def __init__(
        self,
        classifier: Classifier,
        repository: BrainEntryRepository,
        vector_store: VectorStore,
        collector: SlackCollector,
    ) -> None:
        self.classifier = classifier
        self.repository = repository
        self.vector_store = vector_store
        self.collector = collector

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

                # Build entry
                entry_type = extraction.get("type", EntryType.UNCLASSIFIED)
                if isinstance(entry_type, str):
                    try:
                        entry_type = EntryType(entry_type)
                    except ValueError:
                        entry_type = EntryType.UNCLASSIFIED

                entry = BrainEntry(
                    type=entry_type,
                    title=extraction.get("title", text[:60]),
                    summary=extraction.get("summary", text[:200]),
                    raw_content=text,
                    tags=[entry_type.value],
                    slack_ts=ts or None,
                    slack_permalink=msg.get("permalink") or None,
                    author_id=msg.get("user", "unknown"),
                    author_name=msg.get("user_name", "Unknown"),
                    thread_ts=msg.get("thread_ts"),
                    reply_count=msg.get("reply_count", 0),
                    source="slack",
                )

                # Store in SQLite
                await self.repository.save(entry)

                # Store embedding in Qdrant (if available)
                if embedding:
                    await self.vector_store.upsert(
                        id=str(entry.id),
                        vector=embedding,
                        payload={
                            "entry_type": entry.type.value,
                            "created_at": entry.created_at.isoformat(),
                        },
                    )
                    entry.embedding_vector_id = str(entry.id)

                processed += 1
                log.info(
                    "message_processed",
                    entry_id=str(entry.id),
                    type=entry.type.value,
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

        Classifies, embeds, and stores with source='manual'.
        """
        log.info("manual_capture_started", text_length=len(text))

        extraction, embedding = await self.classifier.classify_and_embed(text)

        entry_type = extraction.get("type", EntryType.UNCLASSIFIED)
        if isinstance(entry_type, str):
            try:
                entry_type = EntryType(entry_type)
            except ValueError:
                entry_type = EntryType.UNCLASSIFIED

        entry = BrainEntry(
            type=entry_type,
            title=extraction.get("title", text[:60]),
            summary=extraction.get("summary", text[:200]),
            raw_content=text,
            tags=[entry_type.value],
            slack_ts=None,
            slack_permalink=None,
            author_id="manual",
            author_name=author_name,
            source="manual",
        )

        await self.repository.save(entry)

        if embedding:
            await self.vector_store.upsert(
                id=str(entry.id),
                vector=embedding,
                payload={
                    "entry_type": entry.type.value,
                    "created_at": entry.created_at.isoformat(),
                },
            )
            entry.embedding_vector_id = str(entry.id)

        log.info(
            "manual_capture_complete",
            entry_id=str(entry.id),
            type=entry.type.value,
            title=entry.title,
        )
        return entry
