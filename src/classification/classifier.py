"""Classifier service — wraps LLM provider for classification + embedding."""

import structlog

from src.classification.provider import LLMProvider
from src.core.exceptions import ProviderError
from src.models.enums import EntryType, PARACategory

log = structlog.get_logger(__name__)


class Classifier:
    """Orchestrates classification and embedding via an LLM provider.

    Decouples classification from embedding failures — both are attempted
    independently and failures are handled gracefully.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self.provider = provider

    async def classify_and_embed(
        self, text: str
    ) -> tuple[dict, list[float]]:
        """Classify text and generate embedding.

        Returns:
            tuple of (extraction_dict, embedding_vector)
            - extraction_dict: {"type": EntryType, "title": str, "summary": str,
                "para_category": PARACategory, "confidence": float,
                "entities": list[dict], "project": str|None,
                "action_items": list[str], "keywords": list[str]}
            - embedding_vector: list[float] (empty list if embedding fails)
        """
        # Attempt classification + extraction
        extraction = await self._classify(text)

        # Attempt embedding (independent of classification)
        embedding = await self._embed(text)

        return extraction, embedding

    async def _classify(self, text: str) -> dict:
        """Attempt classification, fall back to truncated text on failure."""
        try:
            return await self.provider.classify_and_extract(text)
        except Exception as e:
            log.error(
                "classification_failed",
                error=str(e),
            )
            return {
                "type": EntryType.UNCLASSIFIED,
                "title": text[:60],
                "summary": text[:200],
                "para_category": PARACategory.RESOURCE,
                "confidence": 0.0,
                "entities": [],
                "project": None,
                "action_items": [],
                "keywords": [],
            }

    async def _embed(self, text: str) -> list[float]:
        """Attempt embedding, return empty list on failure."""
        try:
            return await self.provider.embed(text)
        except Exception as e:
            log.error(
                "embedding_failed",
                error=str(e),
            )
            return []
