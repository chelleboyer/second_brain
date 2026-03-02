"""Tests for Phase 3 enhanced retrieval — multi-signal ranking, recall, and graph-aware search."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.models.brain_entry import BrainEntry, SearchResult
from src.models.enums import EntryType
from src.retrieval.recall import RecallResult, RecallService
from src.retrieval.search import (
    DUAL_MATCH_BOOST,
    RECENCY_HALF_LIFE_DAYS,
    WEIGHT_ENTITY,
    WEIGHT_KEYWORD,
    WEIGHT_RECENCY,
    WEIGHT_VECTOR,
    SearchOrchestrator,
    _entity_overlap_score,
    _recency_score,
)
from tests.conftest import make_entry


# ── Recency Score Tests ──────────────────────────────────────────


class TestRecencyScore:
    """Tests for _recency_score exponential decay."""

    def test_brand_new_entry_scores_near_one(self):
        """An entry created just now should have recency ~1.0."""
        now = datetime.now(timezone.utc)
        score = _recency_score(now)
        assert score > 0.95

    def test_half_life_entry_scores_half(self):
        """An entry created RECENCY_HALF_LIFE_DAYS ago should score ~0.5."""
        then = datetime.now(timezone.utc) - timedelta(days=RECENCY_HALF_LIFE_DAYS)
        score = _recency_score(then)
        assert 0.45 <= score <= 0.55

    def test_very_old_entry_scores_low(self):
        """An entry 180 days old should score very low."""
        then = datetime.now(timezone.utc) - timedelta(days=180)
        score = _recency_score(then)
        assert score < 0.05

    def test_future_entry_scores_one(self):
        """An entry with a future timestamp should not exceed 1.0."""
        future = datetime.now(timezone.utc) + timedelta(days=10)
        score = _recency_score(future)
        assert score >= 1.0


# ── Entity Overlap Score Tests ───────────────────────────────────


class TestEntityOverlapScore:
    """Tests for _entity_overlap_score."""

    def test_no_entities_returns_zero(self):
        assert _entity_overlap_score({"some", "tokens"}, []) == 0.0

    def test_no_overlap_returns_zero(self):
        score = _entity_overlap_score({"unrelated"}, ["FastAPI", "Python"])
        assert score == 0.0

    def test_full_overlap_returns_one(self):
        score = _entity_overlap_score({"fastapi", "python"}, ["FastAPI", "Python"])
        assert score == 1.0

    def test_partial_overlap(self):
        score = _entity_overlap_score({"fastapi", "other"}, ["FastAPI", "Python"])
        assert 0.4 <= score <= 0.6

    def test_multi_word_entity_overlap(self):
        """Multi-word entity: any token matching counts."""
        score = _entity_overlap_score(
            {"machine", "test"}, ["Machine Learning", "Deep Learning"]
        )
        assert score > 0.0


# ── Signal Weights Tests ─────────────────────────────────────────


class TestSignalWeights:
    """Verify signal weight constants sum to 1.0."""

    def test_weights_sum_to_one(self):
        total = WEIGHT_VECTOR + WEIGHT_KEYWORD + WEIGHT_ENTITY + WEIGHT_RECENCY
        assert abs(total - 1.0) < 0.001


# ── Multi-Signal Merge Tests ─────────────────────────────────────


class TestMultiSignalMerge:
    """Tests for SearchOrchestrator._merge_results."""

    def _make_orchestrator(self):
        """Create a minimal orchestrator for merge testing."""
        return SearchOrchestrator(
            provider=MagicMock(),
            vector_store=MagicMock(),
            keyword_search=MagicMock(),
            repository=MagicMock(),
        )

    def test_vector_only_result(self):
        orch = self._make_orchestrator()
        entry = make_entry(title="Vector Only")
        v_results = [SearchResult(entry=entry, score=0.9, source="vector")]
        merged = orch._merge_results(v_results, [], {"test"})
        assert len(merged) == 1
        assert merged[0].source == "vector"

    def test_keyword_only_result(self):
        orch = self._make_orchestrator()
        entry = make_entry(title="Keyword Only")
        k_results = [SearchResult(entry=entry, score=0.8, source="keyword")]
        merged = orch._merge_results([], k_results, {"test"})
        assert len(merged) == 1
        assert merged[0].source == "keyword"

    def test_dual_match_gets_both_source(self):
        orch = self._make_orchestrator()
        entry = make_entry(title="Dual Match")
        v_results = [SearchResult(entry=entry, score=0.8, source="vector")]
        k_results = [SearchResult(entry=entry, score=0.6, source="keyword")]
        merged = orch._merge_results(v_results, k_results, {"test"})
        both = [r for r in merged if r.source == "both"]
        assert len(both) == 1

    def test_dual_match_boosted_score(self):
        """Dual match should apply DUAL_MATCH_BOOST multiplier."""
        orch = self._make_orchestrator()
        entry = make_entry(title="Dual Boost")
        v_results = [SearchResult(entry=entry, score=0.5, source="vector")]
        k_results = [SearchResult(entry=entry, score=0.5, source="keyword")]
        merged = orch._merge_results(v_results, k_results, set())

        # Without boost the score would be lower
        single_entry = make_entry(title="Single")
        v_single = [SearchResult(entry=single_entry, score=0.5, source="vector")]
        single_merged = orch._merge_results(v_single, [], set())

        assert merged[0].score > single_merged[0].score

    def test_entity_overlap_boosts_score(self):
        """Entries with entity overlap should score higher for matching queries."""
        orch = self._make_orchestrator()
        entry_with = make_entry(
            title="Has Entity",
            extracted_entities=["FastAPI", "Python"],
        )
        entry_without = make_entry(title="No Entity")

        v1 = [SearchResult(entry=entry_with, score=0.5, source="vector")]
        v2 = [SearchResult(entry=entry_without, score=0.5, source="vector")]

        merged_with = orch._merge_results(v1, [], {"fastapi"})
        merged_without = orch._merge_results(v2, [], {"fastapi"})

        assert merged_with[0].score > merged_without[0].score


# ── Search Filter Tests ──────────────────────────────────────────


class TestSearchFilters:
    """Tests for entity and type filtering."""

    @pytest.mark.asyncio
    async def test_filter_by_entity(self):
        orch = SearchOrchestrator(
            provider=MagicMock(),
            vector_store=MagicMock(),
            keyword_search=MagicMock(),
            repository=MagicMock(),
        )
        e1 = make_entry(title="Has FastAPI", extracted_entities=["FastAPI"])
        e2 = make_entry(title="No Match", extracted_entities=["Django"])
        results = [
            SearchResult(entry=e1, score=0.8, source="vector"),
            SearchResult(entry=e2, score=0.7, source="vector"),
        ]
        filtered = await orch._filter_by_entity(results, "FastAPI")
        assert len(filtered) == 1
        assert filtered[0].entry.title == "Has FastAPI"

    def test_filter_by_type(self):
        e1 = make_entry(title="Idea", type=EntryType.IDEA)
        e2 = make_entry(title="Task", type=EntryType.TASK)
        results = [
            SearchResult(entry=e1, score=0.8, source="vector"),
            SearchResult(entry=e2, score=0.7, source="vector"),
        ]
        filtered = SearchOrchestrator._filter_by_type(results, "idea")
        assert len(filtered) == 1
        assert filtered[0].entry.title == "Idea"


# ── Entity-Scoped Search Tests ───────────────────────────────────


class TestEntityScopedSearch:
    """Tests for search_by_entity and get_timeline."""

    @pytest.mark.asyncio
    async def test_search_by_entity_no_repo(self):
        """Without entity_repo, returns empty."""
        orch = SearchOrchestrator(
            provider=MagicMock(),
            vector_store=MagicMock(),
            keyword_search=MagicMock(),
            repository=MagicMock(),
        )
        results = await orch.search_by_entity("FastAPI")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_by_entity_with_results(self):
        entry = make_entry(title="FastAPI Entry", confidence=0.9)
        entity = MagicMock()
        entity.id = uuid4()

        entity_repo = MagicMock()
        entity_repo.search_entities_by_name = AsyncMock(return_value=[entity])
        entity_repo.get_entries_for_entity = AsyncMock(
            return_value=[str(entry.id)]
        )

        repository = MagicMock()
        repository.get_by_id = AsyncMock(return_value=entry)

        orch = SearchOrchestrator(
            provider=MagicMock(),
            vector_store=MagicMock(),
            keyword_search=MagicMock(),
            repository=repository,
            entity_repo=entity_repo,
        )
        results = await orch.search_by_entity("FastAPI")
        assert len(results) == 1
        assert results[0].source == "entity"

    @pytest.mark.asyncio
    async def test_get_timeline_ordered_oldest_first(self):
        now = datetime.now(timezone.utc)
        e1 = make_entry(title="Old", created_at=now - timedelta(days=10))
        e2 = make_entry(title="New", created_at=now)

        entity = MagicMock()
        entity.id = uuid4()

        entity_repo = MagicMock()
        entity_repo.search_entities_by_name = AsyncMock(return_value=[entity])
        entity_repo.get_entries_for_entity = AsyncMock(
            return_value=[str(e1.id), str(e2.id)]
        )

        repository = MagicMock()
        repository.get_by_id = AsyncMock(
            side_effect=lambda uid: e1 if uid == e1.id else e2
        )

        orch = SearchOrchestrator(
            provider=MagicMock(),
            vector_store=MagicMock(),
            keyword_search=MagicMock(),
            repository=repository,
            entity_repo=entity_repo,
        )
        results = await orch.get_timeline("Test")
        assert len(results) == 2
        assert results[0].entry.title == "Old"
        assert results[1].entry.title == "New"


# ── Recall Result Tests ──────────────────────────────────────────


class TestRecallResult:
    """Tests for RecallResult model."""

    def test_to_dict(self):
        entry = make_entry(title="Source 1")
        result = RecallResult(
            answer="Test answer",
            sources=[entry],
            search_results=[SearchResult(entry=entry, score=0.8, source="vector")],
            confidence=0.75,
        )
        d = result.to_dict()
        assert d["answer"] == "Test answer"
        assert d["confidence"] == 0.75
        assert d["result_count"] == 1
        assert len(d["sources"]) == 1
        assert d["sources"][0]["title"] == "Source 1"

    def test_empty_result(self):
        result = RecallResult(
            answer="No results", sources=[], search_results=[], confidence=0.0
        )
        d = result.to_dict()
        assert d["result_count"] == 0
        assert d["confidence"] == 0.0


# ── Recall Service Tests ─────────────────────────────────────────


class TestRecallService:
    """Tests for RecallService."""

    def _make_search(self, results: list[SearchResult]) -> MagicMock:
        search = MagicMock()
        search.search = AsyncMock(return_value=results)
        return search

    @pytest.mark.asyncio
    async def test_recall_no_results(self):
        search = self._make_search([])
        svc = RecallService(search=search)
        result = await svc.recall("test question")
        assert result.confidence == 0.0
        assert "No relevant entries" in result.answer

    @pytest.mark.asyncio
    async def test_recall_simple_returns_formatted(self):
        entry = make_entry(title="Test Match", summary="A summary")
        search = self._make_search(
            [SearchResult(entry=entry, score=0.8, source="vector")]
        )
        svc = RecallService(search=search)
        result = await svc.recall_simple("test question")
        assert len(result.sources) == 1
        assert "Test Match" in result.answer

    @pytest.mark.asyncio
    async def test_recall_without_provider_uses_raw(self):
        """Without LLM provider, recall should return raw formatted results."""
        entry = make_entry(title="Raw Result")
        search = self._make_search(
            [SearchResult(entry=entry, score=0.7, source="keyword")]
        )
        svc = RecallService(search=search, provider=None)
        result = await svc.recall("test")
        assert len(result.sources) == 1
        assert "Raw Result" in result.answer

    @pytest.mark.asyncio
    async def test_recall_with_provider(self):
        """With LLM provider, recall should use the provider for synthesis."""
        entry = make_entry(title="Source")
        search = self._make_search(
            [SearchResult(entry=entry, score=0.9, source="vector")]
        )
        provider = MagicMock()
        provider.classify_and_extract = AsyncMock(
            return_value={"summary": "Synthesized answer from Source"}
        )
        svc = RecallService(search=search, provider=provider)
        result = await svc.recall("test question")
        assert result.confidence > 0
        assert len(result.sources) == 1

    @pytest.mark.asyncio
    async def test_recall_provider_failure_degrades(self):
        """If LLM provider fails, should degrade to raw results."""
        entry = make_entry(title="Fallback")
        search = self._make_search(
            [SearchResult(entry=entry, score=0.8, source="vector")]
        )
        provider = MagicMock()
        provider.classify_and_extract = AsyncMock(
            side_effect=Exception("LLM down")
        )
        svc = RecallService(search=search, provider=provider)
        result = await svc.recall("test")
        assert "Fallback" in result.answer

    @pytest.mark.asyncio
    async def test_compute_confidence(self):
        entry = make_entry(title="High", confidence=0.9)
        results = [SearchResult(entry=entry, score=0.9, source="vector")]
        conf = RecallService._compute_confidence(results)
        assert 0.0 < conf <= 1.0

    def test_format_entries_for_prompt(self):
        entry = make_entry(title="My Entry", summary="Summary text")
        output = RecallService._format_entries_for_prompt([entry])
        assert "My Entry" in output
        assert "Summary text" in output
