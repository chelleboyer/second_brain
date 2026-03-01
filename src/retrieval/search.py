"""Dual search orchestrator — merges vector and keyword search results."""

import asyncio
from uuid import UUID

import structlog

from src.classification.provider import LLMProvider
from src.core.exceptions import ProviderError, RetrievalError
from src.models.brain_entry import BrainEntry, SearchResult
from src.retrieval.keyword_search import KeywordSearch
from src.retrieval.vector_store import VectorStore
from src.storage.repository import BrainEntryRepository

log = structlog.get_logger(__name__)

DUAL_MATCH_BOOST = 1.5


class SearchOrchestrator:
    """Orchestrates dual search: vector similarity + keyword matching."""

    def __init__(
        self,
        provider: LLMProvider,
        vector_store: VectorStore,
        keyword_search: KeywordSearch,
        repository: BrainEntryRepository,
    ) -> None:
        self.provider = provider
        self.vector_store = vector_store
        self.keyword_search = keyword_search
        self.repository = repository

    async def search(
        self, query: str, limit: int = 20
    ) -> list[SearchResult]:
        """Run dual search: vector + keyword, merge and boost dual matches.

        Degrades gracefully:
        - If embedding fails: keyword-only results
        - If Qdrant fails: keyword-only results
        - If keyword fails: vector-only results
        """
        # Attempt to embed the query for vector search
        query_vector: list[float] = []
        try:
            query_vector = await self.provider.embed(query)
        except Exception:
            log.warning("search_embedding_failed_using_keyword_only")

        # Run searches in parallel
        vector_results: list[SearchResult] = []
        keyword_results: list[SearchResult] = []

        tasks = []
        if query_vector:
            tasks.append(self._vector_search(query_vector, limit))
        tasks.append(self._keyword_search(query, limit))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        idx = 0
        if query_vector:
            if not isinstance(results[idx], Exception):
                vector_results = results[idx]
            else:
                log.warning("vector_search_failed", error=str(results[idx]))
            idx += 1

        if not isinstance(results[idx], Exception):
            keyword_results = results[idx]
        else:
            log.warning("keyword_search_failed", error=str(results[idx]))

        # Merge results
        merged = self._merge_results(vector_results, keyword_results)

        # Sort by score descending, take top N
        merged.sort(key=lambda r: r.score, reverse=True)
        return merged[:limit]

    async def _vector_search(
        self, query_vector: list[float], limit: int
    ) -> list[SearchResult]:
        """Run vector search and convert to SearchResult."""
        raw_results = await self.vector_store.search(query_vector, limit=limit)
        results: list[SearchResult] = []
        for entry_id, score in raw_results:
            entry = await self.repository.get_by_id(UUID(entry_id))
            if entry:
                results.append(
                    SearchResult(entry=entry, score=score, source="vector")
                )
        return results

    async def _keyword_search(
        self, query: str, limit: int
    ) -> list[SearchResult]:
        """Run keyword search."""
        return await self.keyword_search.search(query, limit=limit)

    def _merge_results(
        self,
        vector_results: list[SearchResult],
        keyword_results: list[SearchResult],
    ) -> list[SearchResult]:
        """Merge vector and keyword results, boosting dual matches."""
        # Index by entry ID
        vector_map: dict[str, SearchResult] = {
            str(r.entry.id): r for r in vector_results
        }
        keyword_map: dict[str, SearchResult] = {
            str(r.entry.id): r for r in keyword_results
        }

        all_ids = set(vector_map.keys()) | set(keyword_map.keys())
        merged: list[SearchResult] = []

        for entry_id in all_ids:
            v_result = vector_map.get(entry_id)
            k_result = keyword_map.get(entry_id)

            if v_result and k_result:
                # Dual match — boost score
                avg_score = (v_result.score + k_result.score) / 2
                boosted = min(avg_score * DUAL_MATCH_BOOST, 1.0)
                merged.append(
                    SearchResult(
                        entry=v_result.entry,
                        score=boosted,
                        source="both",
                    )
                )
            elif v_result:
                merged.append(v_result)
            elif k_result:
                merged.append(k_result)

        return merged
