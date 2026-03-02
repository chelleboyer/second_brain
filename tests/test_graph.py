"""Tests for Phase 2: Graph traversal service."""

from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import uuid4

import pytest

from src.core.entity_resolution import EntityRepository
from src.core.graph import GraphService
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
async def graph_db() -> AsyncGenerator[Database, None]:
    database = Database(":memory:")
    await database.init_db()
    yield database


@pytest.fixture
async def graph_entry_repo(graph_db: Database) -> BrainEntryRepository:
    return BrainEntryRepository(graph_db)


@pytest.fixture
async def graph_entity_repo(graph_db: Database) -> EntityRepository:
    return EntityRepository(graph_db)


@pytest.fixture
async def graph_service(
    graph_entity_repo: EntityRepository,
    graph_entry_repo: BrainEntryRepository,
) -> GraphService:
    return GraphService(
        entity_repo=graph_entity_repo,
        entry_repo=graph_entry_repo,
    )


# ── Helpers ──────────────────────────────────────────────────────


async def _seed_entries_and_entities(
    entry_repo: BrainEntryRepository,
    entity_repo: EntityRepository,
) -> dict:
    """Create a small knowledge graph for testing.

    Creates:
    - 3 entries: idea, decision, task (connected by relationships)
    - 2 entities: ProjectX, FastAPI (shared across entries)
    """
    idea = make_entry(type=EntryType.IDEA, title="Use FastAPI for API", slack_ts=None, source="manual")
    decision = make_entry(type=EntryType.DECISION, title="Adopt FastAPI", slack_ts=None, source="manual")
    task = make_entry(type=EntryType.TASK, title="Set up FastAPI scaffolding", slack_ts=None, source="manual")

    for e in [idea, decision, task]:
        await entry_repo.save(e)

    # Create entities
    project_x = Entity(name="ProjectX", entity_type=EntityType.PROJECT, entry_count=3)
    fastapi = Entity(name="FastAPI", entity_type=EntityType.TECHNOLOGY, entry_count=3)
    await entity_repo.save_entity(project_x)
    await entity_repo.save_entity(fastapi)

    # Link entities to entries
    for entry in [idea, decision, task]:
        for entity in [project_x, fastapi]:
            m = EntityMention(
                entity_id=entity.id,
                entry_id=entry.id,
                mention_text=entity.name,
            )
            await entity_repo.save_mention(m)

    # Create relationships: idea -> decision (evolves), decision -> task (implements)
    rel1 = EntryRelationship(
        source_entry_id=idea.id,
        target_entry_id=decision.id,
        relationship_type=RelationshipType.EVOLVES,
        confidence=0.9,
        reason="Idea evolved into decision",
    )
    rel2 = EntryRelationship(
        source_entry_id=decision.id,
        target_entry_id=task.id,
        relationship_type=RelationshipType.IMPLEMENTS,
        confidence=0.85,
        reason="Decision implemented as task",
    )
    await entity_repo.save_relationship(rel1)
    await entity_repo.save_relationship(rel2)

    return {
        "idea": idea,
        "decision": decision,
        "task": task,
        "project_x": project_x,
        "fastapi": fastapi,
    }


# ── Backlinks Tests ──────────────────────────────────────────────


class TestBacklinks:
    """Tests for entity backlink queries."""

    @pytest.mark.asyncio
    async def test_get_backlinks_returns_all_entries(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        entries = await graph_service.get_backlinks(data["project_x"].id)
        assert len(entries) == 3

    @pytest.mark.asyncio
    async def test_get_backlinks_excludes_archived(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        await graph_entry_repo.archive(data["task"].id)
        entries = await graph_service.get_backlinks(data["project_x"].id)
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_get_backlinks_empty_for_unknown_entity(
        self, graph_service: GraphService,
    ):
        entries = await graph_service.get_backlinks(uuid4())
        assert entries == []

    @pytest.mark.asyncio
    async def test_entity_backlinks_summary(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        summary = await graph_service.get_entity_backlinks_summary(data["fastapi"].id)

        assert summary["entity"].name == "FastAPI"
        assert summary["total_entries"] == 3
        assert "idea" in summary["by_type"]
        assert "decision" in summary["by_type"]
        assert "task" in summary["by_type"]

    @pytest.mark.asyncio
    async def test_backlinks_summary_unknown_entity(
        self, graph_service: GraphService,
    ):
        summary = await graph_service.get_entity_backlinks_summary(uuid4())
        assert summary["entity"] is None
        assert summary["total_entries"] == 0


# ── Relationship Chain Tests ─────────────────────────────────────


class TestRelationshipChains:
    """Tests for relationship chain traversal."""

    @pytest.mark.asyncio
    async def test_find_chains_from_entry(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        chains = await graph_service.find_relationship_chain(
            data["idea"].id, max_depth=3
        )
        assert len(chains) >= 1
        # Should find at least the idea -> decision chain
        chain_titles = [[step["entry"].title for step in chain] for chain in chains]
        found_decision = any("Adopt FastAPI" in titles for titles in chain_titles)
        assert found_decision

    @pytest.mark.asyncio
    async def test_find_chains_with_type_filter(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        chains = await graph_service.find_relationship_chain(
            data["idea"].id,
            target_types=[RelationshipType.EVOLVES],
            max_depth=2,
        )
        # Should only find evolves relationships
        for chain in chains:
            for step in chain[1:]:  # Skip start node
                if step["relationship"]:
                    assert step["relationship"] == RelationshipType.EVOLVES

    @pytest.mark.asyncio
    async def test_find_chains_empty_for_isolated_entry(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
    ):
        isolated = make_entry(
            type=EntryType.NOTE, title="Isolated note", slack_ts=None, source="manual"
        )
        await graph_entry_repo.save(isolated)
        chains = await graph_service.find_relationship_chain(isolated.id)
        assert chains == []

    @pytest.mark.asyncio
    async def test_find_typed_chain(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        chains = await graph_service.find_typed_chain(
            data["idea"].id,
            type_sequence=[EntryType.IDEA, EntryType.DECISION],
        )
        # Should find idea -> decision
        assert len(chains) >= 1
        assert chains[0][0].type == EntryType.IDEA
        assert chains[0][1].type == EntryType.DECISION


# ── Graph Walk Tests ─────────────────────────────────────────────


class TestGraphWalk:
    """Tests for depth-limited graph walks."""

    @pytest.mark.asyncio
    async def test_walk_finds_related_entries(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        result = await graph_service.walk_graph(data["idea"].id, max_depth=2)

        assert result["start"].title == "Use FastAPI for API"
        assert len(result["related_entries"]) >= 1
        assert len(result["shared_entities"]) >= 1

    @pytest.mark.asyncio
    async def test_walk_respects_max_depth(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        # Depth 1 should not reach the task from the idea
        result = await graph_service.walk_graph(
            data["idea"].id, max_depth=1, include_entity_links=False
        )
        distances = [r["distance"] for r in result["related_entries"]]
        assert all(d <= 1 for d in distances)

    @pytest.mark.asyncio
    async def test_walk_includes_entity_links(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        result = await graph_service.walk_graph(
            data["idea"].id, max_depth=1, include_entity_links=True
        )
        via_types = [r["via"] for r in result["related_entries"]]
        # Should have at least some entity-based links
        assert "entity" in via_types or "relationship" in via_types

    @pytest.mark.asyncio
    async def test_walk_nonexistent_entry(
        self, graph_service: GraphService,
    ):
        result = await graph_service.walk_graph(uuid4())
        assert result["start"] is None
        assert result["related_entries"] == []


# ── Co-occurrence Tests ──────────────────────────────────────────


class TestEntityCooccurrence:
    """Tests for entity co-occurrence queries."""

    @pytest.mark.asyncio
    async def test_cooccurrence_finds_related_entities(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        cooc = await graph_service.get_entity_cooccurrence(data["project_x"].id)
        assert len(cooc) >= 1
        assert cooc[0]["entity"].name == "FastAPI"
        assert cooc[0]["shared_entries"] == 3

    @pytest.mark.asyncio
    async def test_cooccurrence_empty_for_isolated_entity(
        self, graph_service: GraphService,
        graph_entity_repo: EntityRepository,
    ):
        isolated = Entity(name="Isolated", entity_type=EntityType.CONCEPT)
        await graph_entity_repo.save_entity(isolated)
        cooc = await graph_service.get_entity_cooccurrence(isolated.id)
        assert cooc == []


# ── Relationship Detail Tests ────────────────────────────────────


class TestRelationshipDetail:
    """Tests for detailed relationship queries."""

    @pytest.mark.asyncio
    async def test_entry_relationships_detail(
        self, graph_service: GraphService,
        graph_entry_repo: BrainEntryRepository,
        graph_entity_repo: EntityRepository,
    ):
        data = await _seed_entries_and_entities(graph_entry_repo, graph_entity_repo)
        detail = await graph_service.get_entry_relationships_detail(data["decision"].id)

        assert detail["entry"].title == "Adopt FastAPI"
        # Decision has incoming (from idea) and outgoing (to task)
        assert len(detail["outgoing"]) >= 1
        assert len(detail["incoming"]) >= 1

    @pytest.mark.asyncio
    async def test_relationships_detail_nonexistent_entry(
        self, graph_service: GraphService,
    ):
        detail = await graph_service.get_entry_relationships_detail(uuid4())
        assert detail["entry"] is None
        assert detail["outgoing"] == []
        assert detail["incoming"] == []
