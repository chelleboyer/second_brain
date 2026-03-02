"""Tests for Phase 2: Semantic entity matching enhancements."""

from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.entity_resolution import (
    DEFAULT_SEMANTIC_THRESHOLDS,
    EntityRepository,
    EntityResolver,
)
from src.models.brain_entry import Entity
from src.models.enums import EntityType
from src.storage.database import Database


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
async def sem_db() -> AsyncGenerator[Database, None]:
    database = Database(":memory:")
    await database.init_db()
    yield database


@pytest.fixture
async def sem_entity_repo(sem_db: Database) -> EntityRepository:
    return EntityRepository(sem_db)


@pytest.fixture
def mock_vector_store() -> MagicMock:
    store = MagicMock()
    store.upsert_entity = AsyncMock()
    store.search_entities = AsyncMock(return_value=[])
    return store


@pytest.fixture
def mock_provider() -> MagicMock:
    provider = MagicMock()
    provider.embed = AsyncMock(return_value=[0.1] * 384)
    return provider


@pytest.fixture
async def resolver_with_semantics(
    sem_entity_repo: EntityRepository,
    mock_vector_store: MagicMock,
    mock_provider: MagicMock,
) -> EntityResolver:
    return EntityResolver(
        entity_repo=sem_entity_repo,
        vector_store=mock_vector_store,
        provider=mock_provider,
    )


@pytest.fixture
async def resolver_without_semantics(
    sem_entity_repo: EntityRepository,
) -> EntityResolver:
    return EntityResolver(entity_repo=sem_entity_repo)


# ── Default Thresholds Tests ─────────────────────────────────────


class TestSemanticThresholds:
    """Tests for configurable semantic similarity thresholds."""

    def test_default_thresholds_exist(self):
        assert EntityType.PERSON in DEFAULT_SEMANTIC_THRESHOLDS
        assert EntityType.TECHNOLOGY in DEFAULT_SEMANTIC_THRESHOLDS
        assert EntityType.CONCEPT in DEFAULT_SEMANTIC_THRESHOLDS

    def test_person_threshold_is_strictest(self):
        assert DEFAULT_SEMANTIC_THRESHOLDS[EntityType.PERSON] >= 0.80

    def test_concept_threshold_is_most_lenient(self):
        assert DEFAULT_SEMANTIC_THRESHOLDS[EntityType.CONCEPT] <= 0.70


# ── Semantic Matching Tests ──────────────────────────────────────


class TestSemanticEntityMatching:
    """Tests for semantic (embedding-based) entity matching."""

    @pytest.mark.asyncio
    async def test_semantic_match_when_fuzzy_fails(
        self,
        resolver_with_semantics: EntityResolver,
        sem_entity_repo: EntityRepository,
        mock_vector_store: MagicMock,
    ):
        # Create an entity that won't match by fuzzy
        entity = Entity(
            name="React Native",
            entity_type=EntityType.TECHNOLOGY,
            entry_count=1,
        )
        await sem_entity_repo.save_entity(entity)

        # Configure vector store to return a match above threshold
        mock_vector_store.search_entities = AsyncMock(
            return_value=[(str(entity.id), 0.85)]
        )

        entry_id = uuid4()
        # "RN" won't fuzzy match "React Native", but semantic will
        extracted = [{"name": "RN Framework", "type": "technology"}]

        resolved = await resolver_with_semantics.resolve_entities(extracted, entry_id)
        assert len(resolved) == 1
        assert resolved[0].id == entity.id  # Matched via semantics

    @pytest.mark.asyncio
    async def test_semantic_match_below_threshold_creates_new(
        self,
        resolver_with_semantics: EntityResolver,
        mock_vector_store: MagicMock,
    ):
        # Vector store returns a match below threshold
        mock_vector_store.search_entities = AsyncMock(
            return_value=[(str(uuid4()), 0.5)]
        )

        entry_id = uuid4()
        extracted = [{"name": "TotallyNew", "type": "concept"}]

        resolved = await resolver_with_semantics.resolve_entities(extracted, entry_id)
        assert len(resolved) == 1
        assert resolved[0].name == "TotallyNew"  # Created new

    @pytest.mark.asyncio
    async def test_no_semantic_match_when_store_empty(
        self,
        resolver_with_semantics: EntityResolver,
        mock_vector_store: MagicMock,
    ):
        mock_vector_store.search_entities = AsyncMock(return_value=[])

        entry_id = uuid4()
        extracted = [{"name": "NewEntity", "type": "technology"}]

        resolved = await resolver_with_semantics.resolve_entities(extracted, entry_id)
        assert len(resolved) == 1
        assert resolved[0].name == "NewEntity"

    @pytest.mark.asyncio
    async def test_fuzzy_match_takes_priority_over_semantic(
        self,
        resolver_with_semantics: EntityResolver,
        sem_entity_repo: EntityRepository,
        mock_vector_store: MagicMock,
    ):
        entity = Entity(
            name="FastAPI",
            entity_type=EntityType.TECHNOLOGY,
            entry_count=1,
        )
        await sem_entity_repo.save_entity(entity)

        entry_id = uuid4()
        # "FastAPI" will match exactly — semantic should NOT be called
        extracted = [{"name": "FastAPI", "type": "technology"}]

        resolved = await resolver_with_semantics.resolve_entities(extracted, entry_id)
        assert len(resolved) == 1
        assert resolved[0].id == entity.id
        # search_entities should not be called since fuzzy matched first
        mock_vector_store.search_entities.assert_not_called()

    @pytest.mark.asyncio
    async def test_graceful_degradation_without_vector_store(
        self,
        resolver_without_semantics: EntityResolver,
    ):
        entry_id = uuid4()
        extracted = [{"name": "NewTech", "type": "technology"}]

        resolved = await resolver_without_semantics.resolve_entities(extracted, entry_id)
        assert len(resolved) == 1
        assert resolved[0].name == "NewTech"


# ── Entity Embedding Tests ───────────────────────────────────────


class TestEntityEmbedding:
    """Tests for entity embedding on creation."""

    @pytest.mark.asyncio
    async def test_new_entity_gets_embedded(
        self,
        resolver_with_semantics: EntityResolver,
        mock_vector_store: MagicMock,
        mock_provider: MagicMock,
    ):
        entry_id = uuid4()
        extracted = [{"name": "NewProject", "type": "project"}]

        await resolver_with_semantics.resolve_entities(extracted, entry_id)

        # embed called for: 1) semantic match search, 2) embedding the new entity
        assert mock_provider.embed.call_count == 2
        mock_vector_store.upsert_entity.assert_called_once()

    @pytest.mark.asyncio
    async def test_existing_match_does_not_re_embed(
        self,
        resolver_with_semantics: EntityResolver,
        sem_entity_repo: EntityRepository,
        mock_vector_store: MagicMock,
        mock_provider: MagicMock,
    ):
        entity = Entity(
            name="ExistingTech",
            entity_type=EntityType.TECHNOLOGY,
            entry_count=1,
        )
        await sem_entity_repo.save_entity(entity)

        entry_id = uuid4()
        extracted = [{"name": "ExistingTech", "type": "technology"}]

        await resolver_with_semantics.resolve_entities(extracted, entry_id)

        # Should NOT embed since it matched an existing entity
        mock_provider.embed.assert_not_called()
        mock_vector_store.upsert_entity.assert_not_called()

    @pytest.mark.asyncio
    async def test_embedding_failure_does_not_block(
        self,
        resolver_with_semantics: EntityResolver,
        mock_provider: MagicMock,
    ):
        mock_provider.embed = AsyncMock(side_effect=Exception("API down"))

        entry_id = uuid4()
        extracted = [{"name": "TestEntity", "type": "concept"}]

        # Should still create the entity even if embedding fails
        resolved = await resolver_with_semantics.resolve_entities(extracted, entry_id)
        assert len(resolved) == 1
        assert resolved[0].name == "TestEntity"


# ── Custom Threshold Tests ───────────────────────────────────────


class TestCustomThresholds:
    """Tests for custom similarity thresholds."""

    @pytest.mark.asyncio
    async def test_custom_threshold_applied(
        self,
        sem_entity_repo: EntityRepository,
        mock_vector_store: MagicMock,
        mock_provider: MagicMock,
    ):
        # Set a very high threshold so nothing matches
        resolver = EntityResolver(
            entity_repo=sem_entity_repo,
            vector_store=mock_vector_store,
            provider=mock_provider,
            semantic_thresholds={EntityType.TECHNOLOGY: 0.99},
        )

        entity = Entity(
            name="SomeFramework",
            entity_type=EntityType.TECHNOLOGY,
            entry_count=1,
        )
        await sem_entity_repo.save_entity(entity)

        # Return high-ish score but below 0.99
        mock_vector_store.search_entities = AsyncMock(
            return_value=[(str(entity.id), 0.90)]
        )

        entry_id = uuid4()
        extracted = [{"name": "DifferentFramework", "type": "technology"}]

        resolved = await resolver.resolve_entities(extracted, entry_id)
        # Should NOT match due to custom high threshold
        assert resolved[0].name == "DifferentFramework"
        assert resolved[0].id != entity.id
