"""Contextual recall — citation-backed answers from stored knowledge."""

from __future__ import annotations

from uuid import UUID

import structlog

from src.classification.provider import LLMProvider
from src.models.brain_entry import BrainEntry, SearchResult
from src.retrieval.search import SearchOrchestrator

log = structlog.get_logger(__name__)

RECALL_PROMPT = """You are a knowledge assistant. Answer the user's question using ONLY the stored knowledge entries provided below.

## Rules:
1. Every claim MUST cite the source entry by its [ENTRY_ID].
2. Clearly separate what the stored knowledge says from any inference you make.
3. If the stored knowledge doesn't fully answer the question, say so explicitly.
4. Format citations inline like: "According to [ENTRY_ID], ..."
5. At the end, list a "Sources" section with entry ID and title for each cited entry.
6. Be concise and actionable.

## Stored Knowledge Entries:
{entries}

## User Question:
{question}

## Answer (with citations):"""


class RecallResult:
    """Structured recall response with answer and source citations."""

    def __init__(
        self,
        answer: str,
        sources: list[BrainEntry],
        search_results: list[SearchResult],
        confidence: float,
    ) -> None:
        self.answer = answer
        self.sources = sources
        self.search_results = search_results
        self.confidence = confidence

    def to_dict(self) -> dict:
        """Serialize for API response."""
        return {
            "answer": self.answer,
            "sources": [
                {
                    "id": str(s.id),
                    "title": s.title,
                    "type": s.type.value,
                    "created_at": s.created_at.isoformat(),
                }
                for s in self.sources
            ],
            "confidence": self.confidence,
            "result_count": len(self.search_results),
        }


class RecallService:
    """Contextual recall with citation-backed answers.

    Separates 'stored knowledge' from 'model reasoning' by:
    1. Searching for relevant entries (multi-signal)
    2. Building a context window from top entries
    3. Asking the LLM to answer with citations only from stored data
    """

    def __init__(
        self,
        search: SearchOrchestrator,
        provider: LLMProvider | None = None,
    ) -> None:
        self.search = search
        self.provider = provider

    async def recall(
        self,
        question: str,
        limit: int = 10,
        *,
        entity_filter: str | None = None,
        type_filter: str | None = None,
        include_neighbors: bool = True,
    ) -> RecallResult:
        """Answer a question using stored knowledge with citations.

        Args:
            question: User's natural-language question.
            limit: Max source entries to feed into context.
            entity_filter: Scope recall to entries mentioning this entity.
            type_filter: Scope recall to a specific EntryType.
            include_neighbors: Include 1-hop graph neighbors in search.

        Returns:
            RecallResult with answer text, source entries, and confidence.
        """
        # Step 1: Search for relevant entries
        results = await self.search.search(
            query=question,
            limit=limit,
            entity_filter=entity_filter,
            type_filter=type_filter,
            include_neighbors=include_neighbors,
        )

        if not results:
            return RecallResult(
                answer="No relevant entries found in your knowledge base for this question.",
                sources=[],
                search_results=[],
                confidence=0.0,
            )

        sources = [r.entry for r in results]

        # If no LLM provider, return raw results without synthesis
        if not self.provider:
            return RecallResult(
                answer=self._format_raw_results(results),
                sources=sources,
                search_results=results,
                confidence=self._compute_confidence(results),
            )

        # Step 2: Build context from entries
        entries_text = self._format_entries_for_prompt(sources)

        # Step 3: Ask LLM to synthesize with citations
        prompt = RECALL_PROMPT.format(
            entries=entries_text, question=question
        )

        try:
            response = await self.provider.classify_and_extract(prompt)
            # The provider returns a dict; we want the raw text answer
            # Since we're repurposing classify_and_extract, extract the summary
            answer = response.get("summary", "") or response.get("title", "")
            if not answer:
                # Fallback: use raw response
                answer = str(response)
        except Exception:
            log.warning("recall_llm_failed_using_raw_results")
            answer = self._format_raw_results(results)

        return RecallResult(
            answer=answer,
            sources=sources,
            search_results=results,
            confidence=self._compute_confidence(results),
        )

    async def recall_simple(
        self, question: str, limit: int = 10
    ) -> RecallResult:
        """Simple recall without LLM synthesis — just search and rank.

        Returns formatted search results with source attribution.
        """
        results = await self.search.search(
            query=question, limit=limit, include_neighbors=True
        )

        if not results:
            return RecallResult(
                answer="No relevant entries found.",
                sources=[],
                search_results=[],
                confidence=0.0,
            )

        sources = [r.entry for r in results]
        return RecallResult(
            answer=self._format_raw_results(results),
            sources=sources,
            search_results=results,
            confidence=self._compute_confidence(results),
        )

    @staticmethod
    def _format_entries_for_prompt(entries: list[BrainEntry]) -> str:
        """Format entries as numbered context for the LLM prompt."""
        parts = []
        for entry in entries:
            parts.append(
                f"[{entry.id}] ({entry.type.value}) {entry.title}\n"
                f"Summary: {entry.summary}\n"
                f"Content: {entry.raw_content[:500]}\n"
                f"Date: {entry.created_at.strftime('%Y-%m-%d')}\n"
                f"Confidence: {entry.confidence:.2f}\n"
            )
        return "\n---\n".join(parts)

    @staticmethod
    def _format_raw_results(results: list[SearchResult]) -> str:
        """Format search results as a readable answer without LLM synthesis."""
        lines = ["Here are the most relevant entries from your knowledge base:\n"]
        for i, r in enumerate(results, 1):
            e = r.entry
            lines.append(
                f"{i}. **{e.title}** ({e.type.value}, {r.score:.0%} match)\n"
                f"   {e.summary}\n"
                f"   Source: {e.source} | {e.created_at.strftime('%Y-%m-%d')}\n"
            )
        return "\n".join(lines)

    @staticmethod
    def _compute_confidence(results: list[SearchResult]) -> float:
        """Compute overall recall confidence from search result scores.

        Uses the average of top-3 scores, weighted by entry confidence.
        """
        if not results:
            return 0.0
        top = results[:3]
        weighted_scores = []
        for r in top:
            entry_conf = r.entry.confidence if r.entry.confidence else 0.5
            weighted_scores.append(r.score * (0.7 + 0.3 * entry_conf))
        return min(sum(weighted_scores) / len(weighted_scores), 1.0)
