"""Tests for Phase 2: Progressive summarization service."""

from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.entity_resolution import EntityRepository
from src.core.summarization import SummarizationService
from src.models.brain_entry import (
    BrainEntry,
    Entity,
    EntityMention,
    EntitySummary,
)
from src.models.enums import EntityType, EntryType
from src.storage.database import Database
from src.storage.repository import BrainEntryRepository
from tests.conftest import make_entry


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
async def summ_db() -> AsyncGenerator[Database, None]:
    database = Database(":memory:")
    await database.init_db()
    yield database


@pytest.fixture
async def summ_entry_repo(summ_db: Database) -> BrainEntryRepository:
    return BrainEntryRepository(summ_db)


@pytest.fixture
async def summ_entity_repo(summ_db: Database) -> EntityRepository:
    return EntityRepository(summ_db)


@pytest.fixture
def mock_provider() -> MagicMock:
    """Mock LLM provider that returns a summary."""
    provider = MagicMock()
    provider.classify_and_extract = AsyncMock(
        return_value={
            "type": "note",
            "title": "Summary",
            "summary": "This is a synthesized summary of the entity's knowledge.",
        }
    )
    provider.embed = AsyncMock(return_value=[0.1] * 384)
    return provider


@pytest.fixture
async def summ_service(
    summ_entity_repo: EntityRepository,
    summ_entry_repo: BrainEntryRepository,
    summ_db: Database,
    mock_provider: MagicMock,
) -> SummarizationService:
    return SummarizationService(
        entity_repo=summ_entity_repo,
        entry_repo=summ_entry_repo,
        db=summ_db,
        provider=mock_provider,
    )


@pytest.fixture
async def summ_service_no_provider(
    summ_entity_repo: EntityRepository,
    summ_entry_repo: BrainEntryRepository,
    summ_db: Database,
) -> SummarizationService:
    return SummarizationService(
        entity_repo=summ_entity_repo,
        entry_repo=summ_entry_repo,
        db=summ_db,
        provider=None,
    )


# ── Helpers ──────────────────────────────────────────────────────


async def _seed_entity_with_entries(
    entry_repo: BrainEntryRepository,
    entity_repo: EntityRepository,
    entry_count: int = 3,
) -> tuple[Entity, list[BrainEntry]]:
    """Create an entity with linked entries."""
    entity = Entity(
        name="FastAPI",
        entity_type=EntityType.TECHNOLOGY,
        entry_count=entry_count,
    )
    await entity_repo.save_entity(entity)

    entries = []
    for i in range(entry_count):
        entry = make_entry(
            type=EntryType.IDEA,
            title=f"FastAPI idea {i}",
            summary=f"Summary about FastAPI feature {i}",
            slack_ts=None,
            source="manual",
        )
        await entry_repo.save(entry)
        entries.append(entry)

        mention = EntityMention(
            entity_id=entity.id,
            entry_id=entry.id,
            mention_text="FastAPI",
        )
        await entity_repo.save_mention(mention)

    return entity, entries


# ── EntitySummary Model Tests ────────────────────────────────────


class TestEntitySummaryModel:
    """Tests for the EntitySummary model."""

    def test_creates_with_defaults(self):
        s = EntitySummary(entity_id=uuid4())
        assert s.summary_text == ""
        assert s.entry_count_at_summary == 0
        assert s.id is not None

    def test_creates_with_values(self):
        s = EntitySummary(
            entity_id=uuid4(),
            summary_text="A great summary.",
            entry_count_at_summary=5,
        )
        assert s.summary_text == "A great summary."
        assert s.entry_count_at_summary == 5


# ── Summary CRUD Tests ──────────────────────────────────────────


class TestSummaryCRUD:
    """Tests for entity summary persistence."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_summary(
        self, summ_service: SummarizationService,
    ):
        entity_id = uuid4()
        summary = EntitySummary(
            entity_id=entity_id,
            summary_text="Test summary.",
            entry_count_at_summary=3,
        )
        await summ_service.save_entity_summary(summary)

        fetched = await summ_service.get_entity_summary(entity_id)
        assert fetched is not None
        assert fetched.summary_text == "Test summary."
        assert fetched.entry_count_at_summary == 3

    @pytest.mark.asyncio
    async def test_get_nonexistent_summary(
        self, summ_service: SummarizationService,
    ):
        result = await summ_service.get_entity_summary(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(
        self, summ_service: SummarizationService,
    ):
        entity_id = uuid4()
        s1 = EntitySummary(
            entity_id=entity_id,
            summary_text="First version.",
            entry_count_at_summary=2,
        )
        await summ_service.save_entity_summary(s1)

        s1.summary_text = "Updated version."
        s1.entry_count_at_summary = 5
        s1.updated_at = datetime.now(timezone.utc)
        await summ_service.save_entity_summary(s1)

        fetched = await summ_service.get_entity_summary(entity_id)
        assert fetched is not None
        assert fetched.summary_text == "Updated version."
        assert fetched.entry_count_at_summary == 5


# ── Staleness Detection Tests ────────────────────────────────────


class TestStalenessDetection:
    """Tests for summary staleness detection."""

    @pytest.mark.asyncio
    async def test_no_summary_with_entries_is_stale(
        self, summ_service: SummarizationService,
        summ_entity_repo: EntityRepository,
        summ_entry_repo: BrainEntryRepository,
    ):
        entity, _ = await _seed_entity_with_entries(
            summ_entry_repo, summ_entity_repo, 2
        )
        assert await summ_service.is_summary_stale(entity.id)

    @pytest.mark.asyncio
    async def test_current_summary_not_stale(
        self, summ_service: SummarizationService,
        summ_entity_repo: EntityRepository,
        summ_entry_repo: BrainEntryRepository,
    ):
        entity, _ = await _seed_entity_with_entries(
            summ_entry_repo, summ_entity_repo, 3
        )
        summary = EntitySummary(
            entity_id=entity.id,
            summary_text="Up to date.",
            entry_count_at_summary=3,
        )
        await summ_service.save_entity_summary(summary)

        assert not await summ_service.is_summary_stale(entity.id)

    @pytest.mark.asyncio
    async def test_outdated_summary_is_stale(
        self, summ_service: SummarizationService,
        summ_entity_repo: EntityRepository,
        summ_entry_repo: BrainEntryRepository,
    ):
        entity, _ = await _seed_entity_with_entries(
            summ_entry_repo, summ_entity_repo, 5
        )
        summary = EntitySummary(
            entity_id=entity.id,
            summary_text="Older summary.",
            entry_count_at_summary=2,
        )
        await summ_service.save_entity_summary(summary)

        assert await summ_service.is_summary_stale(entity.id)

    @pytest.mark.asyncio
    async def test_unknown_entity_not_stale(
        self, summ_service: SummarizationService,
    ):
        assert not await summ_service.is_summary_stale(uuid4())


# ── Summarization Tests ──────────────────────────────────────────


class TestSummarization:
    """Tests for per-entity summarization."""

    @pytest.mark.asyncio
    async def test_summarize_entity_creates_summary(
        self, summ_service: SummarizationService,
        summ_entity_repo: EntityRepository,
        summ_entry_repo: BrainEntryRepository,
    ):
        entity, _ = await _seed_entity_with_entries(
            summ_entry_repo, summ_entity_repo, 3
        )
        result = await summ_service.summarize_entity(entity.id)
        assert result is not None
        assert result.summary_text != ""
        assert result.entry_count_at_summary == 3

    @pytest.mark.asyncio
    async def test_summarize_skips_when_current(
        self, summ_service: SummarizationService,
        summ_entity_repo: EntityRepository,
        summ_entry_repo: BrainEntryRepository,
        mock_provider: MagicMock,
    ):
        entity, _ = await _seed_entity_with_entries(
            summ_entry_repo, summ_entity_repo, 3
        )
        # Create a current summary
        summary = EntitySummary(
            entity_id=entity.id,
            summary_text="Already current.",
            entry_count_at_summary=3,
        )
        await summ_service.save_entity_summary(summary)

        # Reset call count
        mock_provider.classify_and_extract.reset_mock()

        result = await summ_service.summarize_entity(entity.id)
        assert result is not None
        assert result.summary_text == "Already current."
        # Provider should NOT have been called
        mock_provider.classify_and_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_summarize_force_regenerates(
        self, summ_service: SummarizationService,
        summ_entity_repo: EntityRepository,
        summ_entry_repo: BrainEntryRepository,
        mock_provider: MagicMock,
    ):
        entity, _ = await _seed_entity_with_entries(
            summ_entry_repo, summ_entity_repo, 3
        )
        summary = EntitySummary(
            entity_id=entity.id,
            summary_text="Already current.",
            entry_count_at_summary=3,
        )
        await summ_service.save_entity_summary(summary)

        mock_provider.classify_and_extract.reset_mock()
        result = await summ_service.summarize_entity(entity.id, force=True)
        mock_provider.classify_and_extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_summarize_unknown_entity_returns_none(
        self, summ_service: SummarizationService,
    ):
        result = await summ_service.summarize_entity(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_summarize_without_provider_returns_none(
        self, summ_service_no_provider: SummarizationService,
        summ_entity_repo: EntityRepository,
        summ_entry_repo: BrainEntryRepository,
    ):
        entity, _ = await _seed_entity_with_entries(
            summ_entry_repo, summ_entity_repo, 3
        )
        result = await summ_service_no_provider.summarize_entity(entity.id)
        assert result is None


# ── Strategic Summary Tests ──────────────────────────────────────


class TestStrategicSummary:
    """Tests for cross-entity strategic summarization."""

    @pytest.mark.asyncio
    async def test_strategic_summary_from_specific_entities(
        self, summ_service: SummarizationService,
        summ_entity_repo: EntityRepository,
        summ_entry_repo: BrainEntryRepository,
    ):
        e1, _ = await _seed_entity_with_entries(
            summ_entry_repo, summ_entity_repo, 2
        )
        e2 = Entity(name="Qdrant", entity_type=EntityType.TECHNOLOGY, entry_count=2)
        await summ_entity_repo.save_entity(e2)

        # Create summaries for both
        for entity in [e1, e2]:
            s = EntitySummary(
                entity_id=entity.id,
                summary_text=f"Summary about {entity.name}.",
                entry_count_at_summary=2,
            )
            await summ_service.save_entity_summary(s)

        result = await summ_service.strategic_summary([e1.id, e2.id])
        assert result is not None

    @pytest.mark.asyncio
    async def test_strategic_summary_no_summaries_returns_none(
        self, summ_service: SummarizationService,
    ):
        result = await summ_service.strategic_summary([uuid4(), uuid4()])
        assert result is None

    @pytest.mark.asyncio
    async def test_strategic_summary_without_provider_returns_none(
        self, summ_service_no_provider: SummarizationService,
    ):
        result = await summ_service_no_provider.strategic_summary()
        assert result is None


# ── Format Helpers Tests ─────────────────────────────────────────


class TestFormatHelpers:
    """Tests for the entry formatting helper."""

    def test_format_entries_respects_max(self):
        entries = [
            make_entry(
                title=f"Entry {i}",
                summary=f"Summary {i}",
                slack_ts=None,
                source="manual",
            )
            for i in range(25)
        ]
        text = SummarizationService._format_entries_for_prompt(entries, max_entries=5)
        assert "Entry 4" in text
        assert "Entry 5" not in text
        assert "20 more entries" in text

    def test_format_entries_empty(self):
        text = SummarizationService._format_entries_for_prompt([])
        assert text == ""
