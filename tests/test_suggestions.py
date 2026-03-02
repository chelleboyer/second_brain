"""Tests for Phase 2: Smart suggestions engine."""

from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator
from uuid import uuid4

import pytest

from src.core.entity_resolution import EntityRepository
from src.core.graph import GraphService
from src.core.suggestions import (
    Suggestion,
    SuggestionEngine,
    TYPE_SUGGESTION_RULES,
)
from src.models.brain_entry import (
    BrainEntry,
    Entity,
    EntityMention,
    EntryRelationship,
)
from src.models.enums import (
    EntityType,
    EntryType,
    RelationshipType,
)
from src.storage.database import Database
from src.storage.repository import BrainEntryRepository
from tests.conftest import make_entry


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
async def sugg_db() -> AsyncGenerator[Database, None]:
    database = Database(":memory:")
    await database.init_db()
    yield database


@pytest.fixture
async def sugg_entry_repo(sugg_db: Database) -> BrainEntryRepository:
    return BrainEntryRepository(sugg_db)


@pytest.fixture
async def sugg_entity_repo(sugg_db: Database) -> EntityRepository:
    return EntityRepository(sugg_db)


@pytest.fixture
async def sugg_graph_service(
    sugg_entity_repo: EntityRepository,
    sugg_entry_repo: BrainEntryRepository,
) -> GraphService:
    return GraphService(sugg_entity_repo, sugg_entry_repo)


@pytest.fixture
async def suggestion_engine(
    sugg_entity_repo: EntityRepository,
    sugg_entry_repo: BrainEntryRepository,
    sugg_graph_service: GraphService,
) -> SuggestionEngine:
    return SuggestionEngine(
        entity_repo=sugg_entity_repo,
        entry_repo=sugg_entry_repo,
        graph_service=sugg_graph_service,
    )


# ── Suggestion Model Tests ──────────────────────────────────────


class TestSuggestionModel:
    """Tests for the Suggestion model."""

    def test_suggestion_creates(self):
        s = Suggestion(
            suggestion_type="type_link",
            message="Related decisions:",
        )
        assert s.suggestion_type == "type_link"
        assert s.related_entries == []

    def test_suggestion_to_dict(self):
        entry = make_entry(
            title="Test entry",
            type=EntryType.DECISION,
            slack_ts=None,
            source="manual",
        )
        entity = Entity(name="ProjectX", entity_type=EntityType.PROJECT)
        s = Suggestion(
            suggestion_type="type_link",
            message="Related entries:",
            related_entries=[entry],
            related_entities=[entity],
            action="summarize",
        )
        d = s.to_dict()
        assert d["suggestion_type"] == "type_link"
        assert len(d["related_entries"]) == 1
        assert d["related_entries"][0]["title"] == "Test entry"
        assert len(d["related_entities"]) == 1
        assert d["related_entities"][0]["name"] == "ProjectX"
        assert d["action"] == "summarize"


# ── Type Suggestion Rules ────────────────────────────────────────


class TestTypeSuggestionRules:
    """Tests for type-based suggestion rule configuration."""

    def test_risk_has_rules(self):
        assert EntryType.RISK in TYPE_SUGGESTION_RULES
        rules = TYPE_SUGGESTION_RULES[EntryType.RISK]
        assert len(rules) >= 1
        look_for_types = [t for r in rules for t in r["look_for"]]
        assert EntryType.DECISION in look_for_types

    def test_task_has_rules(self):
        assert EntryType.TASK in TYPE_SUGGESTION_RULES

    def test_note_has_no_rules(self):
        # Notes are generic — no specific suggestions
        assert EntryType.NOTE not in TYPE_SUGGESTION_RULES


# ── Type-Based Suggestion Tests ──────────────────────────────────


class TestTypeSuggestions:
    """Tests for type-based suggestion generation."""

    @pytest.mark.asyncio
    async def test_risk_suggests_decisions(
        self, suggestion_engine: SuggestionEngine,
        sugg_entry_repo: BrainEntryRepository,
        sugg_entity_repo: EntityRepository,
    ):
        # Create a decision about ProjectX
        decision = make_entry(
            type=EntryType.DECISION,
            title="Decide on risk mitigation",
            slack_ts=None,
            source="manual",
        )
        await sugg_entry_repo.save(decision)

        # Create entity and link
        entity = Entity(name="ProjectX", entity_type=EntityType.PROJECT, entry_count=2)
        await sugg_entity_repo.save_entity(entity)
        m = EntityMention(entity_id=entity.id, entry_id=decision.id, mention_text="ProjectX")
        await sugg_entity_repo.save_mention(m)

        # Capture a risk about the same entity
        risk = make_entry(
            type=EntryType.RISK,
            title="Risk: data loss in ProjectX",
            slack_ts=None,
            source="manual",
        )
        await sugg_entry_repo.save(risk)
        m2 = EntityMention(entity_id=entity.id, entry_id=risk.id, mention_text="ProjectX")
        await sugg_entity_repo.save_mention(m2)

        suggestions = await suggestion_engine.generate_suggestions(risk, [entity])
        type_link_suggestions = [s for s in suggestions if s.suggestion_type == "type_link"]
        assert len(type_link_suggestions) >= 1
        # Should include the decision
        all_related = [e for s in type_link_suggestions for e in s.related_entries]
        assert any(e.id == decision.id for e in all_related)

    @pytest.mark.asyncio
    async def test_no_suggestions_without_entities(
        self, suggestion_engine: SuggestionEngine,
        sugg_entry_repo: BrainEntryRepository,
    ):
        note = make_entry(
            type=EntryType.NOTE,
            title="Just a note",
            slack_ts=None,
            source="manual",
        )
        await sugg_entry_repo.save(note)

        suggestions = await suggestion_engine.generate_suggestions(note, [])
        assert len(suggestions) == 0


# ── Proactive Suggestion Tests ───────────────────────────────────


class TestProactiveSuggestions:
    """Tests for proactive activity-based suggestions."""

    @pytest.mark.asyncio
    async def test_proactive_when_frequent_entity_mentions(
        self, suggestion_engine: SuggestionEngine,
        sugg_entry_repo: BrainEntryRepository,
        sugg_entity_repo: EntityRepository,
    ):
        entity = Entity(name="ProjectX", entity_type=EntityType.PROJECT, entry_count=4)
        await sugg_entity_repo.save_entity(entity)

        # Create 4 recent entries all mentioning the entity
        entries = []
        for i in range(4):
            entry = make_entry(
                type=EntryType.IDEA,
                title=f"ProjectX idea {i}",
                slack_ts=None,
                source="manual",
            )
            await sugg_entry_repo.save(entry)
            entries.append(entry)
            m = EntityMention(
                entity_id=entity.id, entry_id=entry.id, mention_text="ProjectX"
            )
            await sugg_entity_repo.save_mention(m)

        # Trigger with latest entry
        latest = entries[-1]
        suggestions = await suggestion_engine.generate_suggestions(latest, [entity])
        proactive = [s for s in suggestions if s.suggestion_type == "proactive"]
        assert len(proactive) >= 1
        assert "ProjectX" in proactive[0].message

    @pytest.mark.asyncio
    async def test_no_proactive_for_new_entity(
        self, suggestion_engine: SuggestionEngine,
        sugg_entry_repo: BrainEntryRepository,
        sugg_entity_repo: EntityRepository,
    ):
        entity = Entity(name="BrandNew", entity_type=EntityType.CONCEPT, entry_count=1)
        await sugg_entity_repo.save_entity(entity)

        entry = make_entry(
            type=EntryType.IDEA,
            title="BrandNew idea",
            slack_ts=None,
            source="manual",
        )
        await sugg_entry_repo.save(entry)

        suggestions = await suggestion_engine.generate_suggestions(entry, [entity])
        proactive = [s for s in suggestions if s.suggestion_type == "proactive"]
        assert len(proactive) == 0


# ── Entity-Based Suggestion Tests ────────────────────────────────


class TestEntityBasedSuggestions:
    """Tests for entity co-occurrence-based suggestions."""

    @pytest.mark.asyncio
    async def test_entity_overlap_suggestions(
        self, suggestion_engine: SuggestionEngine,
        sugg_entry_repo: BrainEntryRepository,
        sugg_entity_repo: EntityRepository,
    ):
        # Create two entities
        e1 = Entity(name="ProjectX", entity_type=EntityType.PROJECT, entry_count=2)
        e2 = Entity(name="FastAPI", entity_type=EntityType.TECHNOLOGY, entry_count=2)
        await sugg_entity_repo.save_entity(e1)
        await sugg_entity_repo.save_entity(e2)

        # Create an existing entry sharing both entities
        existing = make_entry(
            title="ProjectX uses FastAPI",
            type=EntryType.ARCH_NOTE,
            slack_ts=None,
            source="manual",
        )
        await sugg_entry_repo.save(existing)
        for e in [e1, e2]:
            m = EntityMention(entity_id=e.id, entry_id=existing.id, mention_text=e.name)
            await sugg_entity_repo.save_mention(m)

        # New entry also sharing both entities
        new_entry = make_entry(
            title="ProjectX FastAPI endpoint design",
            type=EntryType.IDEA,
            slack_ts=None,
            source="manual",
        )
        await sugg_entry_repo.save(new_entry)
        for e in [e1, e2]:
            m = EntityMention(entity_id=e.id, entry_id=new_entry.id, mention_text=e.name)
            await sugg_entity_repo.save_mention(m)

        suggestions = await suggestion_engine.generate_suggestions(new_entry, [e1, e2])
        overlap = [s for s in suggestions if s.suggestion_type == "entity_overlap"]
        assert len(overlap) >= 1
        assert any(e.id == existing.id for e in overlap[0].related_entries)


# ── On-Demand Suggestion Tests ───────────────────────────────────


class TestOnDemandSuggestions:
    """Tests for get_suggestions_for_entry (on-demand)."""

    @pytest.mark.asyncio
    async def test_returns_suggestions_for_existing_entry(
        self, suggestion_engine: SuggestionEngine,
        sugg_entry_repo: BrainEntryRepository,
        sugg_entity_repo: EntityRepository,
    ):
        entity = Entity(name="Qdrant", entity_type=EntityType.TECHNOLOGY, entry_count=1)
        await sugg_entity_repo.save_entity(entity)

        entry = make_entry(
            type=EntryType.IDEA,
            title="Use Qdrant for vectors",
            extracted_entities=["Qdrant"],
            slack_ts=None,
            source="manual",
        )
        await sugg_entry_repo.save(entry)
        m = EntityMention(entity_id=entity.id, entry_id=entry.id, mention_text="Qdrant")
        await sugg_entity_repo.save_mention(m)

        # Call on-demand (won't find type suggestions but exercises the path)
        suggestions = await suggestion_engine.get_suggestions_for_entry(entry.id)
        # At minimum, should run without errors
        assert isinstance(suggestions, list)

    @pytest.mark.asyncio
    async def test_returns_empty_for_unknown_entry(
        self, suggestion_engine: SuggestionEngine,
    ):
        suggestions = await suggestion_engine.get_suggestions_for_entry(uuid4())
        assert suggestions == []
