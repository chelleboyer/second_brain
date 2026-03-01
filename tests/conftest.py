"""Shared test fixtures for Second Brain tests."""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.brain_entry import BrainEntry
from src.models.enums import EntryType
from src.storage.database import Database
from src.storage.repository import BrainEntryRepository


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db() -> AsyncGenerator[Database, None]:
    """In-memory SQLite database with schema initialized."""
    database = Database(":memory:")
    await database.init_db()
    yield database


@pytest.fixture
async def repository(db: Database) -> BrainEntryRepository:
    """Repository connected to the in-memory database."""
    return BrainEntryRepository(db)


@pytest.fixture
def sample_entry() -> BrainEntry:
    """Factory-style fixture returning a default BrainEntry."""
    return BrainEntry(
        id=uuid4(),
        type=EntryType.IDEA,
        title="Test Idea",
        summary="A test idea for unit testing.",
        raw_content="This is a raw test message about a new idea.",
        created_at=datetime.now(timezone.utc),
        tags=["idea"],
        slack_ts="1234567890.123456",
        slack_permalink="https://slack.com/msg/C123/p123",
        author_id="U12345",
        author_name="TestUser",
        source="slack",
    )


def make_entry(**overrides) -> BrainEntry:
    """Create a BrainEntry with sensible defaults, overridable per field."""
    defaults = {
        "id": uuid4(),
        "type": EntryType.IDEA,
        "title": "Test Entry",
        "summary": "A test entry summary.",
        "raw_content": "Raw content of the test entry.",
        "created_at": datetime.now(timezone.utc),
        "tags": ["idea"],
        "slack_ts": str(uuid4()),  # Unique per call
        "slack_permalink": "https://slack.com/msg/C123/p123",
        "author_id": "U12345",
        "author_name": "TestUser",
        "source": "slack",
    }
    defaults.update(overrides)
    return BrainEntry(**defaults)


@pytest.fixture
def mock_hf_provider() -> MagicMock:
    """Mocked HuggingFaceProvider with configurable responses."""
    provider = MagicMock()
    provider.classify_and_extract = AsyncMock(
        return_value={
            "type": EntryType.IDEA,
            "title": "Mock Title",
            "summary": "Mock summary of the content.",
        }
    )
    provider.embed = AsyncMock(
        return_value=[0.1] * 384  # 384-dim vector
    )
    return provider


@pytest.fixture
def mock_classifier() -> MagicMock:
    """Mocked Classifier returning extraction dict + embedding."""
    classifier = MagicMock()
    classifier.classify_and_embed = AsyncMock(
        return_value=(
            {
                "type": EntryType.IDEA,
                "title": "Mock Title",
                "summary": "Mock summary.",
            },
            [0.1] * 384,
        )
    )
    return classifier


@pytest.fixture
def mock_vector_store() -> MagicMock:
    """Mocked VectorStore."""
    store = MagicMock()
    store.init_collection = AsyncMock()
    store.upsert = AsyncMock()
    store.search = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_collector() -> MagicMock:
    """Mocked SlackCollector."""
    collector = MagicMock()
    collector.collect_new_messages = AsyncMock(return_value=[])
    return collector
