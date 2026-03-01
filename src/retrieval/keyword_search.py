"""Keyword search via SQLite FTS5."""

import structlog

from src.models.brain_entry import BrainEntry, SearchResult
from src.storage.repository import BrainEntryRepository

log = structlog.get_logger(__name__)


class KeywordSearch:
    """Thin wrapper around repository FTS5 search for SearchResult interface."""

    def __init__(self, repository: BrainEntryRepository) -> None:
        self.repository = repository

    async def search(
        self, query: str, limit: int = 20
    ) -> list[SearchResult]:
        """Search entries by keyword using FTS5.

        Returns SearchResult objects with source="keyword" and normalized scores.
        """
        results = await self.repository.search_keyword(query, limit=limit)
        return [
            SearchResult(
                entry=entry,
                score=self._normalize_bm25(rank),
                source="keyword",
            )
            for entry, rank in results
        ]

    @staticmethod
    def _normalize_bm25(bm25_score: float) -> float:
        """Normalize BM25 score to [0, 1] range.

        BM25 returns negative values where lower (more negative) = better match.
        Formula: 1 / (1 + abs(score))
        """
        return 1.0 / (1.0 + abs(bm25_score))
