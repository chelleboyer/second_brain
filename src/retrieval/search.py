"""Multi-signal search orchestrator — merges vector, keyword, entity, and recency signals."""

import asyncio
import math
from datetime import datetime, timezone
from uuid import UUID

import structlog

from src.classification.provider import LLMProvider
from src.core.exceptions import ProviderError, RetrievalError
from src.models.brain_entry import BrainEntry, SearchResult
from src.retrieval.keyword_search import KeywordSearch
from src.retrieval.vector_store import VectorStore
from src.storage.repository import BrainEntryRepository

log = structlog.get_logger(__name__)

# ── Signal weights for multi-signal ranking ──────────────────────
WEIGHT_VECTOR = 0.40
WEIGHT_KEYWORD = 0.30
WEIGHT_ENTITY = 0.15
WEIGHT_RECENCY = 0.15

# Dual-match still gets a boost on top of weighted score
DUAL_MATCH_BOOST = 1.2

# Recency half-life in days: entries this old get 0.5 recency score
RECENCY_HALF_LIFE_DAYS = 30.0


def _recency_score(created_at: datetime) -> float:
    """Exponential decay recency score. Recent entries score higher.

    Uses half-life of RECENCY_HALF_LIFE_DAYS so a 30-day-old entry gets 0.5.
    """
    now = datetime.now(timezone.utc)
    age_days = max((now - created_at).total_seconds() / 86400.0, 0.0)
    return math.exp(-0.693 * age_days / RECENCY_HALF_LIFE_DAYS)


def _entity_overlap_score(
    query_tokens: set[str], entry_entities: list[str]
) -> float:
    """Score based on how many query tokens overlap with entry's extracted entities.

    Returns 0.0-1.0: fraction of entity names that overlap with query tokens.
    """
    if not entry_entities:
        return 0.0
    matches = 0
    for entity in entry_entities:
        entity_tokens = set(entity.lower().split())
        if query_tokens & entity_tokens:
            matches += 1
    return min(matches / max(len(entry_entities), 1), 1.0)


class SearchOrchestrator:
    """Orchestrates multi-signal search: vector + keyword + entity overlap + recency."""

    def __init__(
        self,
        provider: LLMProvider,
        vector_store: VectorStore,
        keyword_search: KeywordSearch,
        repository: BrainEntryRepository,
        entity_repo=None,
        graph_service=None,
    ) -> None:
        self.provider = provider
        self.vector_store = vector_store
        self.keyword_search = keyword_search
        self.repository = repository
        self.entity_repo = entity_repo
        self.graph_service = graph_service

    async def search(
        self,
        query: str,
        limit: int = 20,
        *,
        entity_filter: str | None = None,
        type_filter: str | None = None,
        include_neighbors: bool = False,
    ) -> list[SearchResult]:
        """Run multi-signal search with optional graph-aware neighbor expansion.

        Signals combined:
        1. Vector similarity (semantic)
        2. Keyword BM25 (lexical)
        3. Entity overlap (query tokens matching extracted entities)
        4. Recency (exponential decay)

        Args:
            query: Search query text.
            limit: Max results to return.
            entity_filter: If set, only return entries mentioning this entity.
            type_filter: If set, only return entries of this EntryType.
            include_neighbors: If True, expand results with 1-hop relationship neighbors.

        Degrades gracefully:
        - If embedding fails → keyword-only
        - If Qdrant fails → keyword-only
        - If keyword fails → vector-only
        """
        query_tokens = set(query.lower().split())

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
            tasks.append(self._vector_search(query_vector, limit * 2))
        tasks.append(self._keyword_search(query, limit * 2))

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

        # Merge with multi-signal ranking
        merged = self._merge_results(
            vector_results, keyword_results, query_tokens
        )

        # Apply entity filter (entity-scoped search)
        if entity_filter:
            merged = await self._filter_by_entity(merged, entity_filter)

        # Apply type filter
        if type_filter:
            merged = self._filter_by_type(merged, type_filter)

        # Sort by score descending, take top N
        merged.sort(key=lambda r: r.score, reverse=True)
        top_results = merged[:limit]

        # Phase 3A: Graph-aware search — expand with 1-hop neighbors
        if include_neighbors and self.graph_service:
            top_results = await self._expand_with_neighbors(
                top_results, query_tokens, limit
            )

        return top_results

    async def search_by_entity(
        self, entity_name: str, limit: int = 50
    ) -> list[SearchResult]:
        """Entity-scoped search: return all entries mentioning this entity.

        Returns entries ordered by recency with a relevance score based on
        confidence and recency.
        """
        if not self.entity_repo:
            return []

        entities = await self.entity_repo.search_entities_by_name(entity_name)
        if not entities:
            return []

        seen_entry_ids: set[str] = set()
        results: list[SearchResult] = []

        for entity in entities:
            entry_ids = await self.entity_repo.get_entries_for_entity(entity.id)
            for eid_str in entry_ids:
                if eid_str in seen_entry_ids:
                    continue
                seen_entry_ids.add(eid_str)
                entry = await self.repository.get_by_id(UUID(eid_str))
                if entry and not entry.archived_at:
                    recency = _recency_score(entry.created_at)
                    confidence = entry.confidence if entry.confidence else 0.5
                    score = 0.6 * confidence + 0.4 * recency
                    results.append(
                        SearchResult(entry=entry, score=score, source="entity")
                    )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    async def get_timeline(
        self, entity_name: str, limit: int = 100
    ) -> list[SearchResult]:
        """Timeline view: chronological knowledge evolution for an entity.

        Returns entries mentioning the entity ordered oldest-first.
        """
        if not self.entity_repo:
            return []

        entities = await self.entity_repo.search_entities_by_name(entity_name)
        if not entities:
            return []

        seen: set[str] = set()
        results: list[SearchResult] = []

        for entity in entities:
            entry_ids = await self.entity_repo.get_entries_for_entity(entity.id)
            for eid_str in entry_ids:
                if eid_str in seen:
                    continue
                seen.add(eid_str)
                entry = await self.repository.get_by_id(UUID(eid_str))
                if entry:
                    results.append(
                        SearchResult(entry=entry, score=1.0, source="entity")
                    )

        # Timeline: oldest first
        results.sort(key=lambda r: r.entry.created_at)
        return results[:limit]

    # ── Private helpers ──────────────────────────────────────────

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
        query_tokens: set[str],
    ) -> list[SearchResult]:
        """Merge results using multi-signal weighted ranking.

        Signals:
        - Vector similarity score (WEIGHT_VECTOR)
        - Keyword BM25 score (WEIGHT_KEYWORD)
        - Entity overlap (WEIGHT_ENTITY)
        - Recency decay (WEIGHT_RECENCY)
        """
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

            # Pick entry from whichever result exists
            entry = (v_result or k_result).entry  # type: ignore[union-attr]

            # Compute individual signal scores
            v_score = v_result.score if v_result else 0.0
            k_score = k_result.score if k_result else 0.0
            e_score = _entity_overlap_score(
                query_tokens, entry.extracted_entities or []
            )
            r_score = _recency_score(entry.created_at)

            # Weighted combination
            combined = (
                WEIGHT_VECTOR * v_score
                + WEIGHT_KEYWORD * k_score
                + WEIGHT_ENTITY * e_score
                + WEIGHT_RECENCY * r_score
            )

            # Confidence boost: higher confidence entries get slight advantage
            confidence = entry.confidence if entry.confidence else 0.5
            combined *= (0.9 + 0.2 * confidence)  # 0.9x to 1.1x multiplier

            # Dual match boost
            source = "vector"
            if v_result and k_result:
                combined = min(combined * DUAL_MATCH_BOOST, 1.0)
                source = "both"
            elif k_result:
                source = "keyword"

            merged.append(
                SearchResult(entry=entry, score=combined, source=source)
            )

        return merged

    async def _filter_by_entity(
        self, results: list[SearchResult], entity_name: str
    ) -> list[SearchResult]:
        """Keep only results whose entries mention the given entity."""
        name_lower = entity_name.lower()
        filtered = []
        for r in results:
            entities = r.entry.extracted_entities or []
            if any(name_lower in e.lower() for e in entities):
                filtered.append(r)
        return filtered

    @staticmethod
    def _filter_by_type(
        results: list[SearchResult], type_value: str
    ) -> list[SearchResult]:
        """Keep only results matching the given EntryType value."""
        return [r for r in results if r.entry.type.value == type_value]

    async def _expand_with_neighbors(
        self,
        results: list[SearchResult],
        query_tokens: set[str],
        limit: int,
    ) -> list[SearchResult]:
        """Expand search results with 1-hop relationship neighbors.

        Neighbor entries get a discounted score (0.6x of the parent's score).
        """
        existing_ids = {str(r.entry.id) for r in results}
        neighbor_results: list[SearchResult] = []

        for r in results[:10]:  # Only expand top 10 to avoid explosion
            try:
                rels = await self.graph_service.get_entry_relationships_detail(
                    r.entry.id
                )
                for direction in ("outgoing", "incoming"):
                    for rel in rels.get(direction, []):
                        neighbor_id = (
                            rel["target_entry_id"]
                            if direction == "outgoing"
                            else rel["source_entry_id"]
                        )
                        if str(neighbor_id) in existing_ids:
                            continue
                        existing_ids.add(str(neighbor_id))
                        neighbor = await self.repository.get_by_id(neighbor_id)
                        if neighbor and not neighbor.archived_at:
                            # Discounted score
                            neighbor_score = r.score * 0.6
                            neighbor_results.append(
                                SearchResult(
                                    entry=neighbor,
                                    score=neighbor_score,
                                    source="graph",
                                )
                            )
            except Exception:
                log.debug("neighbor_expansion_failed", entry_id=str(r.entry.id))

        all_results = results + neighbor_results
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:limit]
