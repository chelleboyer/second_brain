"""Tests for entity resolution, entity repository, and novelty detection."""

import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

import pytest

from src.core.entity_resolution import EntityRepository, EntityResolver
from src.models.brain_entry import BrainEntry, Entity, EntityMention, EntryRelationship
from src.models.enums import (
    EntityType,
    EntryType,
    NoveltyVerdict,
    PARACategory,
    RelationshipType,
)
from src.storage.database import Database

from tests.conftest import make_entry


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
async def entity_db() -> AsyncGenerator[Database, None]:
    """In-memory SQLite database with full schema including entity tables."""
    database = Database(":memory:")
    await database.init_db()
    yield database


@pytest.fixture
async def entity_repo(entity_db: Database) -> EntityRepository:
    return EntityRepository(entity_db)


@pytest.fixture
async def resolver(entity_repo: EntityRepository) -> EntityResolver:
    return EntityResolver(entity_repo)


# ── Entity Model Tests ──────────────────────────────────────────


class TestEntityModel:
    """Tests for the Entity Pydantic model."""

    def test_entity_creates_with_defaults(self):
        e = Entity(name="FastAPI", entity_type=EntityType.TECHNOLOGY)
        assert e.name == "FastAPI"
        assert e.entity_type == EntityType.TECHNOLOGY
        assert e.aliases == []
        assert e.entry_count == 0
        assert e.id is not None

    def test_entity_with_aliases(self):
        e = Entity(
            name="Second Brain",
            entity_type=EntityType.PROJECT,
            aliases=["SB", "brain"],
        )
        assert len(e.aliases) == 2
        assert "SB" in e.aliases


class TestEntityMentionModel:
    """Tests for the EntityMention model."""

    def test_creates_with_required_fields(self):
        m = EntityMention(
            entity_id=uuid4(),
            entry_id=uuid4(),
            mention_text="FastAPI",
        )
        assert m.mention_text == "FastAPI"
        assert m.id is not None


class TestEntryRelationshipModel:
    """Tests for the EntryRelationship model."""

    def test_creates_with_required_fields(self):
        r = EntryRelationship(
            source_entry_id=uuid4(),
            target_entry_id=uuid4(),
            relationship_type=RelationshipType.EVOLVES,
        )
        assert r.relationship_type == RelationshipType.EVOLVES
        assert r.confidence == 0.0

    def test_all_relationship_types(self):
        expected = {"supports", "contradicts", "evolves", "implements", "blocks", "related_to"}
        assert {t.value for t in RelationshipType} == expected


# ── Entity Repository Tests ─────────────────────────────────────


class TestEntityRepository:
    """Tests for EntityRepository CRUD operations."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_entity(self, entity_repo: EntityRepository):
        entity = Entity(
            name="Qdrant",
            entity_type=EntityType.TECHNOLOGY,
            description="Vector database",
        )
        await entity_repo.save_entity(entity)

        fetched = await entity_repo.get_entity_by_id(entity.id)
        assert fetched is not None
        assert fetched.name == "Qdrant"
        assert fetched.entity_type == EntityType.TECHNOLOGY

    @pytest.mark.asyncio
    async def test_search_by_name(self, entity_repo: EntityRepository):
        entity = Entity(name="FastAPI", entity_type=EntityType.TECHNOLOGY)
        await entity_repo.save_entity(entity)

        results = await entity_repo.search_entities_by_name("fast")
        assert len(results) == 1
        assert results[0].name == "FastAPI"

    @pytest.mark.asyncio
    async def test_search_by_alias(self, entity_repo: EntityRepository):
        entity = Entity(
            name="Second Brain",
            entity_type=EntityType.PROJECT,
            aliases=["SB", "brain-project"],
        )
        await entity_repo.save_entity(entity)

        results = await entity_repo.search_entities_by_name("brain-project")
        assert len(results) == 1
        assert results[0].name == "Second Brain"

    @pytest.mark.asyncio
    async def test_increment_entry_count(self, entity_repo: EntityRepository):
        entity = Entity(name="Python", entity_type=EntityType.TECHNOLOGY)
        await entity_repo.save_entity(entity)

        await entity_repo.increment_entry_count(entity.id)
        await entity_repo.increment_entry_count(entity.id)

        fetched = await entity_repo.get_entity_by_id(entity.id)
        assert fetched is not None
        assert fetched.entry_count == 2

    @pytest.mark.asyncio
    async def test_save_and_get_mention(self, entity_repo: EntityRepository):
        entity_id = uuid4()
        entry_id = uuid4()
        mention = EntityMention(
            entity_id=entity_id, entry_id=entry_id, mention_text="Python"
        )
        await entity_repo.save_mention(mention)

        mentions = await entity_repo.get_mentions_for_entry(entry_id)
        assert len(mentions) == 1
        assert mentions[0].mention_text == "Python"

    @pytest.mark.asyncio
    async def test_get_entries_for_entity(self, entity_repo: EntityRepository):
        entity_id = uuid4()
        entry1 = uuid4()
        entry2 = uuid4()

        for eid in [entry1, entry2]:
            m = EntityMention(
                entity_id=entity_id, entry_id=eid, mention_text="test"
            )
            await entity_repo.save_mention(m)

        linked = await entity_repo.get_entries_for_entity(entity_id)
        assert len(linked) == 2

    @pytest.mark.asyncio
    async def test_save_and_get_relationship(self, entity_repo: EntityRepository):
        rel = EntryRelationship(
            source_entry_id=uuid4(),
            target_entry_id=uuid4(),
            relationship_type=RelationshipType.SUPPORTS,
            confidence=0.9,
            reason="Same topic",
        )
        await entity_repo.save_relationship(rel)

        # Get relationships for source entry
        rels = await entity_repo.get_relationships_for_entry(rel.source_entry_id)
        assert len(rels) == 1
        assert rels[0].relationship_type == RelationshipType.SUPPORTS
        assert rels[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_get_all_entities(self, entity_repo: EntityRepository):
        e1 = Entity(name="A", entity_type=EntityType.CONCEPT, entry_count=5)
        e2 = Entity(name="B", entity_type=EntityType.PERSON, entry_count=10)
        await entity_repo.save_entity(e1)
        await entity_repo.save_entity(e2)

        all_ents = await entity_repo.get_all_entities()
        assert len(all_ents) == 2
        # Should be ordered by entry_count desc
        assert all_ents[0].name == "B"


# ── Entity Resolver Tests ───────────────────────────────────────


class TestEntityResolver:
    """Tests for entity resolution and novelty detection."""

    @pytest.mark.asyncio
    async def test_creates_new_entity_when_no_match(self, resolver: EntityResolver):
        entry_id = uuid4()
        extracted = [{"name": "Kubernetes", "type": "technology"}]

        resolved = await resolver.resolve_entities(extracted, entry_id)
        assert len(resolved) == 1
        assert resolved[0].name == "Kubernetes"
        assert resolved[0].entity_type == EntityType.TECHNOLOGY

    @pytest.mark.asyncio
    async def test_matches_existing_entity(self, resolver: EntityResolver, entity_repo: EntityRepository):
        # Pre-create an entity
        entity = Entity(name="FastAPI", entity_type=EntityType.TECHNOLOGY, entry_count=1)
        await entity_repo.save_entity(entity)

        entry_id = uuid4()
        extracted = [{"name": "FastAPI", "type": "technology"}]

        resolved = await resolver.resolve_entities(extracted, entry_id)
        assert len(resolved) == 1
        assert resolved[0].id == entity.id  # Matched, not created new

        # entry_count should have been incremented
        fetched = await entity_repo.get_entity_by_id(entity.id)
        assert fetched is not None
        assert fetched.entry_count == 2

    @pytest.mark.asyncio
    async def test_adds_alias_on_variant_match(self, resolver: EntityResolver, entity_repo: EntityRepository):
        entity = Entity(name="FastAPI", entity_type=EntityType.TECHNOLOGY, entry_count=1)
        await entity_repo.save_entity(entity)

        entry_id = uuid4()
        # Use a slightly different name that will match via fuzzy
        extracted = [{"name": "fastapi", "type": "technology"}]

        resolved = await resolver.resolve_entities(extracted, entry_id)
        assert len(resolved) == 1
        assert resolved[0].id == entity.id

    @pytest.mark.asyncio
    async def test_novelty_new_when_no_overlap(self, resolver: EntityResolver):
        # New entity with no prior entries
        entity = Entity(name="BrandNew", entity_type=EntityType.CONCEPT, entry_count=0)
        entry_id = uuid4()

        verdict, augments = await resolver.assess_novelty([entity], entry_id)
        assert verdict == NoveltyVerdict.NEW
        assert augments is None

    @pytest.mark.asyncio
    async def test_novelty_augment_when_shared_entities(
        self, resolver: EntityResolver, entity_repo: EntityRepository
    ):
        # Create two entities that are both linked to an existing entry
        existing_entry_id = uuid4()
        entity_a = Entity(name="ProjectX", entity_type=EntityType.PROJECT, entry_count=2)
        entity_b = Entity(name="FastAPI", entity_type=EntityType.TECHNOLOGY, entry_count=2)
        await entity_repo.save_entity(entity_a)
        await entity_repo.save_entity(entity_b)

        # Link both to the same existing entry
        for ent in [entity_a, entity_b]:
            m = EntityMention(
                entity_id=ent.id, entry_id=existing_entry_id, mention_text=ent.name
            )
            await entity_repo.save_mention(m)

        # Now assess novelty for a new entry sharing both entities
        new_entry_id = uuid4()
        # Also link new entry mentions so they appear in get_entries_for_entity
        for ent in [entity_a, entity_b]:
            m = EntityMention(
                entity_id=ent.id, entry_id=new_entry_id, mention_text=ent.name
            )
            await entity_repo.save_mention(m)

        verdict, augments = await resolver.assess_novelty(
            [entity_a, entity_b], new_entry_id
        )
        assert verdict == NoveltyVerdict.AUGMENT
        assert augments == existing_entry_id


# ── Similarity Function Tests ───────────────────────────────────


class TestSimilarity:
    """Tests for the bigram similarity function."""

    def test_identical_strings(self):
        assert EntityResolver._similarity("hello", "hello") == 1.0

    def test_empty_or_short_strings(self):
        assert EntityResolver._similarity("a", "b") == 0.0
        assert EntityResolver._similarity("", "") == 1.0

    def test_similar_strings(self):
        score = EntityResolver._similarity("fastapi", "fastap")
        assert score > 0.7

    def test_dissimilar_strings(self):
        score = EntityResolver._similarity("python", "kubernetes")
        assert score < 0.3


# ── Enhanced BrainEntry Fields Tests ─────────────────────────────


class TestEnhancedBrainEntry:
    """Tests for Phase 1 enhanced fields on BrainEntry."""

    def test_para_category_default(self):
        entry = BrainEntry(
            type=EntryType.IDEA,
            title="T",
            summary="S",
            raw_content="R",
            author_id="U",
            author_name="N",
        )
        assert entry.para_category == PARACategory.RESOURCE

    def test_confidence_range(self):
        entry = BrainEntry(
            type=EntryType.IDEA,
            title="T",
            summary="S",
            raw_content="R",
            author_id="U",
            author_name="N",
            confidence=0.85,
        )
        assert entry.confidence == 0.85

    def test_extracted_entities_default(self):
        entry = BrainEntry(
            type=EntryType.IDEA,
            title="T",
            summary="S",
            raw_content="R",
            author_id="U",
            author_name="N",
        )
        assert entry.extracted_entities == []

    def test_novelty_default(self):
        entry = BrainEntry(
            type=EntryType.IDEA,
            title="T",
            summary="S",
            raw_content="R",
            author_id="U",
            author_name="N",
        )
        assert entry.novelty == NoveltyVerdict.NEW
        assert entry.augments_entry_id is None

    def test_all_para_categories(self):
        expected = {"project", "area", "resource", "archive"}
        assert {c.value for c in PARACategory} == expected

    def test_all_entity_types(self):
        expected = {"project", "person", "technology", "concept", "organization"}
        assert {t.value for t in EntityType} == expected

    def test_all_novelty_verdicts(self):
        expected = {"new", "augment", "duplicate"}
        assert {v.value for v in NoveltyVerdict} == expected
