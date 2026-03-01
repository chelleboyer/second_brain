"""Tests for the capture pipeline orchestration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.pipeline import CapturePipeline
from src.models.enums import EntryType


class TestCapturePipeline:
    """Tests for the CapturePipeline service."""

    @pytest.fixture
    def pipeline(self, mock_classifier, mock_vector_store, mock_collector, repository):
        """Pipeline with mocked dependencies (real repository)."""
        return CapturePipeline(
            classifier=mock_classifier,
            repository=repository,
            vector_store=mock_vector_store,
            collector=mock_collector,
        )

    @pytest.fixture
    def sample_messages(self):
        """Sample Slack messages for testing."""
        return [
            {
                "ts": "111.001",
                "text": "We should build a new API",
                "user": "U123",
                "user_name": "Alice",
                "permalink": "https://slack.com/msg1",
                "thread_ts": None,
                "reply_count": 0,
            },
            {
                "ts": "111.002",
                "text": "Decision: use Python for backend",
                "user": "U456",
                "user_name": "Bob",
                "permalink": "https://slack.com/msg2",
                "thread_ts": None,
                "reply_count": 3,
            },
        ]

    @pytest.mark.asyncio
    async def test_process_messages_end_to_end(
        self, pipeline, sample_messages, mock_vector_store
    ):
        """process_messages stores entries in DB and Qdrant."""
        processed, failed = await pipeline.process_messages(sample_messages)
        assert processed == 2
        assert failed == 0
        # Vector store should have been called twice
        assert mock_vector_store.upsert.call_count == 2

    @pytest.mark.asyncio
    async def test_duplicate_slack_ts_skipped(
        self, pipeline, sample_messages
    ):
        """Duplicate messages (same slack_ts) are skipped."""
        # Process once
        await pipeline.process_messages(sample_messages)
        # Process same messages again
        processed, failed = await pipeline.process_messages(sample_messages)
        assert processed == 0  # All skipped as duplicates

    @pytest.mark.asyncio
    async def test_classification_failure_stores_unclassified(
        self, pipeline, mock_classifier, sample_messages
    ):
        """Classification failure → entry stored as Unclassified."""
        mock_classifier.classify_and_embed = AsyncMock(
            return_value=(
                {
                    "type": EntryType.UNCLASSIFIED,
                    "title": "We should build a n",
                    "summary": "We should build a new API",
                },
                [0.1] * 384,
            )
        )

        processed, failed = await pipeline.process_messages(
            [sample_messages[0]]
        )
        assert processed == 1
        assert failed == 0

        # Verify entry was stored as Unclassified
        entries = await pipeline.repository.get_recent(limit=10)
        assert any(e.type == EntryType.UNCLASSIFIED for e in entries)

    @pytest.mark.asyncio
    async def test_embedding_failure_still_stores_in_sqlite(
        self, pipeline, mock_classifier, mock_vector_store, sample_messages
    ):
        """Embedding failure → entry still saved to SQLite, Qdrant skipped."""
        mock_classifier.classify_and_embed = AsyncMock(
            return_value=(
                {
                    "type": EntryType.IDEA,
                    "title": "API Idea",
                    "summary": "Build a new API",
                },
                [],  # Empty embedding
            )
        )

        processed, failed = await pipeline.process_messages(
            [sample_messages[0]]
        )
        assert processed == 1
        # Vector store should NOT have been called (empty embedding)
        assert mock_vector_store.upsert.call_count == 0

    @pytest.mark.asyncio
    async def test_catch_up_calls_collector_then_process(
        self, pipeline, mock_collector, sample_messages
    ):
        """catch_up collects messages then processes them."""
        mock_collector.collect_new_messages = AsyncMock(
            return_value=sample_messages
        )

        processed, failed = await pipeline.catch_up()
        assert processed == 2
        mock_collector.collect_new_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_catch_up_no_messages(self, pipeline, mock_collector):
        """catch_up with no new messages returns (0, 0)."""
        mock_collector.collect_new_messages = AsyncMock(return_value=[])
        processed, failed = await pipeline.catch_up()
        assert processed == 0
        assert failed == 0

    @pytest.mark.asyncio
    async def test_capture_manual_creates_manual_entry(self, pipeline):
        """capture_manual creates entry with source='manual' and no slack_ts."""
        entry = await pipeline.capture_manual(
            "A manual thought", author_name="Michelle"
        )

        assert entry.source == "manual"
        assert entry.slack_ts is None
        assert entry.slack_permalink is None
        assert entry.author_id == "manual"
        assert entry.author_name == "Michelle"
        assert entry.type == EntryType.IDEA  # From mock classifier
