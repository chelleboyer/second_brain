"""LLM provider protocol and Hugging Face Inference API implementation."""

import json
import re
from typing import Protocol, runtime_checkable

import httpx
import structlog

from src.core.exceptions import ProviderError
from src.models.enums import CLASSIFIABLE_TYPES, EntryType, EntityType, PARACategory

log = structlog.get_logger(__name__)

CLASSIFICATION_PROMPT = """Analyze the following message and return a JSON object with these fields:

1. "type": one of [idea, task, decision, risk, arch_note, strategy, note]
2. "title": a concise title (max 10 words)
3. "summary": a 1-2 sentence summary
4. "para_category": one of [project, area, resource, archive]
   - "project" = active effort with a specific goal/deadline
   - "area" = ongoing responsibility with no end date
   - "resource" = reference material or topic of interest
   - "archive" = inactive/completed item
5. "confidence": how confident you are in the classification (0.0 to 1.0)
6. "entities": array of objects, each with "name" (string) and "type" (one of [project, person, technology, concept, organization])
   - Extract ALL named entities: project names, people, technologies, concepts, orgs
7. "project": if the message is clearly about a specific project, its name (or null)
8. "action_items": array of action item strings extracted from the message (empty if none)
9. "keywords": array of 3-5 key topic words for search indexing

Respond with ONLY valid JSON, no other text.

Message: {text}"""


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for LLM provider abstraction."""

    async def classify_and_extract(self, text: str) -> dict:
        """Classify text and extract title + summary.

        Returns dict with keys: type (EntryType), title (str), summary (str).
        """
        ...

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        ...


class HuggingFaceProvider:
    """Hugging Face Inference API implementation of LLMProvider."""

    CHAT_URL = "https://router.huggingface.co/v1/chat/completions"
    EMBEDDING_URL = "https://router.huggingface.co/hf-inference/models"

    def __init__(
        self,
        api_token: str,
        classification_model: str,
        embedding_model: str,
    ) -> None:
        self.api_token = api_token
        self.classification_model = classification_model
        self.embedding_model = embedding_model
        self.headers = {"Authorization": f"Bearer {api_token}"}

    async def classify_and_extract(self, text: str) -> dict:
        """Classify text and extract title, summary, entities, PARA category, and more.

        Returns dict with keys: type (EntryType), title (str), summary (str),
        para_category (PARACategory), confidence (float), entities (list[dict]),
        project (str|None), action_items (list[str]), keywords (list[str]).
        Raises ProviderError on total failure after retries.
        """
        prompt = CLASSIFICATION_PROMPT.format(text=text[:2000])  # Truncate long messages
        url = self.CHAT_URL
        payload = {
            "model": self.classification_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
        }

        try:
            response_text = await self._post_with_retry(url, payload)
        except Exception as e:
            log.error(
                "classification_api_failed",
                error=str(e),
            )
            return self._fallback_extraction(text)

        # Parse JSON response
        try:
            parsed = self._extract_json(response_text)
            return self._build_extraction(parsed, text)
        except Exception as e:
            log.warning(
                "classification_parse_failed",
                error=str(e),
                response=response_text[:200],
            )
            # Fallback: try to extract type via regex
            entry_type = self._regex_extract_type(response_text)
            result = self._fallback_extraction(text)
            result["type"] = entry_type
            return result

    def _build_extraction(self, parsed: dict, original_text: str) -> dict:
        """Build a fully structured extraction dict from parsed LLM output."""
        entry_type = self._parse_type(parsed.get("type", ""))
        title = str(parsed.get("title", original_text[:60]))[:100]
        summary = str(parsed.get("summary", original_text[:200]))[:500]

        # PARA category
        para_raw = str(parsed.get("para_category", "resource")).strip().lower()
        try:
            para_category = PARACategory(para_raw)
        except ValueError:
            para_category = PARACategory.RESOURCE

        # Confidence
        try:
            confidence = float(parsed.get("confidence", 0.0))
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0

        # Entities
        raw_entities = parsed.get("entities", [])
        entities: list[dict] = []
        if isinstance(raw_entities, list):
            for ent in raw_entities:
                if isinstance(ent, dict) and "name" in ent:
                    ent_type = str(ent.get("type", "concept")).strip().lower()
                    try:
                        EntityType(ent_type)
                    except ValueError:
                        ent_type = "concept"
                    entities.append({"name": str(ent["name"]), "type": ent_type})

        # Project
        project = parsed.get("project")
        if project and isinstance(project, str):
            project = project.strip() or None
        else:
            project = None

        # Action items
        raw_actions = parsed.get("action_items", [])
        action_items: list[str] = []
        if isinstance(raw_actions, list):
            action_items = [str(a) for a in raw_actions if a]

        # Keywords
        raw_keywords = parsed.get("keywords", [])
        keywords: list[str] = []
        if isinstance(raw_keywords, list):
            keywords = [str(k) for k in raw_keywords if k]

        return {
            "type": entry_type,
            "title": title,
            "summary": summary,
            "para_category": para_category,
            "confidence": confidence,
            "entities": entities,
            "project": project,
            "action_items": action_items,
            "keywords": keywords,
        }

    @staticmethod
    def _fallback_extraction(text: str) -> dict:
        """Minimal fallback when classification fails entirely."""
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

    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector via HF Inference API.

        Raises ProviderError on total failure after retries.
        """
        url = f"{self.EMBEDDING_URL}/{self.embedding_model}"
        payload = {"inputs": text[:1000]}  # Truncate for embedding model

        response_text = await self._post_with_retry(url, payload)

        try:
            result = json.loads(response_text)
            # HF returns either a list of floats or a nested list
            if isinstance(result, list) and len(result) > 0:
                if isinstance(result[0], float):
                    return result
                if isinstance(result[0], list):
                    return result[0]
            raise ValueError(f"Unexpected embedding format: {type(result)}")
        except (json.JSONDecodeError, ValueError) as e:
            raise ProviderError(
                "Failed to parse embedding response",
                details={"error": str(e), "response": response_text[:200]},
            ) from e

    async def _post_with_retry(
        self, url: str, payload: dict, max_retries: int = 3
    ) -> str:
        """POST to HF API with exponential backoff retry."""
        import asyncio

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        url, json=payload, headers=self.headers
                    )
                    if response.status_code == 200:
                        return response.text
                    if response.status_code == 503:
                        # Model loading — wait and retry
                        wait_time = 2 ** (attempt + 1)
                        log.info(
                            "model_loading",
                            url=url,
                            retry_in=wait_time,
                            attempt=attempt + 1,
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    response.raise_for_status()
            except httpx.HTTPStatusError as e:
                last_error = e
                log.warning(
                    "hf_api_error",
                    status=e.response.status_code,
                    attempt=attempt + 1,
                )
            except httpx.RequestError as e:
                last_error = e
                log.warning(
                    "hf_request_error", error=str(e), attempt=attempt + 1
                )

            if attempt < max_retries - 1:
                import asyncio

                await asyncio.sleep(2 ** (attempt + 1))

        raise ProviderError(
            f"HF API failed after {max_retries} attempts",
            details={"url": url, "error": str(last_error)},
        )

    def _extract_json(self, text: str) -> dict:
        """Extract JSON object from response text."""
        # Try direct parse first
        try:
            result = json.loads(text)
            # Chat completions response: {"choices": [{"message": {"content": "..."}}]}
            if isinstance(result, dict) and "choices" in result:
                content = result["choices"][0]["message"]["content"]
                return self._parse_json_content(content)
            # HF text-generation returns list of dicts
            if isinstance(result, list) and len(result) > 0:
                generated = result[0].get("generated_text", text)
                return json.loads(generated)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

        # Try to find JSON in the text
        return self._parse_json_content(text)

    def _parse_json_content(self, text: str) -> dict:
        """Parse JSON from a content string, with regex fallback."""
        # Try direct parse
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Try to find JSON in the text
        json_match = re.search(r"\{[^{}]+\}", text)
        if json_match:
            return json.loads(json_match.group())

        raise ValueError(f"No JSON found in response: {text[:200]}")

    def _parse_type(self, type_str: str) -> EntryType:
        """Parse a type string into EntryType, defaulting to NOTE."""
        type_lower = type_str.strip().lower().replace(" ", "_")
        valid_values = {t.value for t in CLASSIFIABLE_TYPES}
        if type_lower in valid_values:
            return EntryType(type_lower)
        log.warning("unknown_type_defaulting_to_note", raw_type=type_str)
        return EntryType.NOTE

    def _regex_extract_type(self, text: str) -> EntryType:
        """Last-resort regex extraction of type from free text."""
        text_lower = text.lower()
        for entry_type in CLASSIFIABLE_TYPES:
            if entry_type.value in text_lower:
                return entry_type
        return EntryType.NOTE
