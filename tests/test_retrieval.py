"""Tests for retrieval layer — dual search orchestration."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.brain_entry import BrainEntry, SearchResult
from src.models.enums import EntryType
from src.retrieval.search import SearchOrchestrator
from tests.conftest import make_entry


class TestSearchOrchestrator:
    """Tests for the dual search orchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked dependencies."""
        vector_store = MagicMock()
        vector_store.search = AsyncMock(return_value=[])
        keyword_search = MagicMock()
        keyword_search.search = AsyncMock(return_value=[])
        provider = MagicMock()
        provider.embed = AsyncMock(return_value=[0.1] * 384)
        repository = MagicMock()
        repository.get_by_id = AsyncMock(return_value=None)

        orch = SearchOrchestrator(
            vector_store=vector_store,
            keyword_search=keyword_search,
            provider=provider,
            repository=repository,
        )
        return orch, vector_store, keyword_search, provider, repository

    @pytest.mark.asyncio
    async def test_merges_vector_and_keyword_results(self, orchestrator):
        """Results from both sources are merged."""
        orch, vector_store, keyword_search, provider, repository = orchestrator

        entry1 = make_entry(title="Vector Match")
        entry2 = make_entry(title="Keyword Match")

        vector_store.search = AsyncMock(
            return_value=[(str(entry1.id), 0.85)]
        )
        keyword_search.search = AsyncMock(
            return_value=[
                SearchResult(entry=entry2, score=0.7, source="keyword")
            ]
        )

        repository.get_by_id = AsyncMock(return_value=entry1)

        results = await orch.search("test query")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_dual_match_gets_both_source_and_boost(self, orchestrator):
        """Entries appearing in both get source='both' and boosted score."""
        orch, vector_store, keyword_search, provider, repository = orchestrator

        entry = make_entry(title="Dual Match")

        vector_store.search = AsyncMock(
            return_value=[(str(entry.id), 0.8)]
        )
        keyword_search.search = AsyncMock(
            return_value=[
                SearchResult(entry=entry, score=0.6, source="keyword")
            ]
        )

        repository.get_by_id = AsyncMock(return_value=entry)

        results = await orch.search("test")

        dual = [r for r in results if r.source == "both"]
        assert len(dual) == 1
        # Boosted: avg(0.8, 0.6) * 1.5 = 1.05 → capped at 1.0
        assert dual[0].score <= 1.0

    @pytest.mark.asyncio
    async def test_vector_only_result_has_vector_source(self, orchestrator):
        """Vector-only results have source='vector'."""
        orch, vector_store, keyword_search, provider, repository = orchestrator

        entry = make_entry(title="Vector Only")
        vector_store.search = AsyncMock(
            return_value=[(str(entry.id), 0.9)]
        )

        repository.get_by_id = AsyncMock(return_value=entry)

        results = await orch.search("test")
        vector_results = [r for r in results if r.source == "vector"]
        assert len(vector_results) >= 1

    @pytest.mark.asyncio
    async def test_keyword_only_result_has_keyword_source(self, orchestrator):
        """Keyword-only results have source='keyword'."""
        orch, vector_store, keyword_search, provider, repository = orchestrator

        entry = make_entry(title="Keyword Only")
        keyword_search.search = AsyncMock(
            return_value=[
                SearchResult(entry=entry, score=0.75, source="keyword")
            ]
        )

        results = await orch.search("test")
        keyword_results = [r for r in results if r.source == "keyword"]
        assert len(keyword_results) >= 1

    @pytest.mark.asyncio
    async def test_degrades_to_keyword_when_qdrant_fails(self, orchestrator):
        """If Qdrant fails, keyword results are still returned."""
        orch, vector_store, keyword_search, provider, repository = orchestrator

        entry = make_entry(title="Fallback")
        vector_store.search = AsyncMock(side_effect=Exception("Qdrant down"))
        keyword_search.search = AsyncMock(
            return_value=[
                SearchResult(entry=entry, score=0.5, source="keyword")
            ]
        )

        results = await orch.search("test")
        assert len(results) >= 1
        assert all(r.source == "keyword" for r in results)

    @pytest.mark.asyncio
    async def test_degrades_to_keyword_when_embedding_fails(self, orchestrator):
        """If embedding fails, keyword results are still returned."""
        orch, vector_store, keyword_search, provider, repository = orchestrator

        provider.embed = AsyncMock(side_effect=Exception("Embed broken"))
        entry = make_entry(title="Keyword Fallback")
        keyword_search.search = AsyncMock(
            return_value=[
                SearchResult(entry=entry, score=0.6, source="keyword")
            ]
        )

        results = await orch.search("test")
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_results_sorted_by_score_descending(self, orchestrator):
        """Results are sorted highest score first."""
        orch, vector_store, keyword_search, provider, repository = orchestrator

        e1 = make_entry(title="Low")
        e2 = make_entry(title="High")

        keyword_search.search = AsyncMock(
            return_value=[
                SearchResult(entry=e1, score=0.3, source="keyword"),
                SearchResult(entry=e2, score=0.9, source="keyword"),
            ]
        )

        results = await orch.search("test")
        assert len(results) == 2
        assert results[0].score >= results[1].score
