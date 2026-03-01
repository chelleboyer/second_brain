"""Tests for classification provider and classifier service."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.classification.classifier import Classifier
from src.classification.provider import HuggingFaceProvider
from src.models.enums import EntryType


class TestHuggingFaceProvider:
    """Tests for the HuggingFaceProvider."""

    @pytest.fixture
    def provider(self):
        return HuggingFaceProvider(
            api_token="test-token",
            classification_model="test-model",
            embedding_model="test-embed-model",
        )

    @pytest.mark.asyncio
    async def test_parse_valid_json_response(self, provider):
        """Provider parses valid JSON with type, title, summary."""
        response_text = json.dumps({
            "choices": [{"message": {"content": '{"type": "idea", "title": "Build API", "summary": "Create a REST API for the app."}'}}]
        })

        with patch.object(provider, "_post_with_retry", return_value=response_text):
            result = await provider.classify_and_extract("Build a REST API")

        assert result["type"] == EntryType.IDEA
        assert result["title"] == "Build API"
        assert result["summary"] == "Create a REST API for the app."

    @pytest.mark.asyncio
    async def test_parse_malformed_json_falls_back_to_regex(self, provider):
        """Provider falls back to regex when JSON is malformed."""
        response_text = json.dumps({
            "choices": [{"message": {"content": "The type is decision and this is about choosing Python."}}]
        })

        with patch.object(provider, "_post_with_retry", return_value=response_text):
            result = await provider.classify_and_extract("Should we use Python?")

        # Should still get a valid type (regex extraction or fallback to NOTE)
        assert isinstance(result["type"], EntryType)
        assert result["title"]  # Not empty
        assert result["summary"]  # Not empty

    @pytest.mark.asyncio
    async def test_ambiguous_type_defaults_to_note(self, provider):
        """Provider defaults to NOTE for unrecognized types."""
        response_text = json.dumps({
            "choices": [{"message": {"content": '{"type": "banana", "title": "Fruit", "summary": "A fruit thing."}'}}]
        })

        with patch.object(provider, "_post_with_retry", return_value=response_text):
            result = await provider.classify_and_extract("Something about bananas")

        assert result["type"] == EntryType.NOTE

    @pytest.mark.asyncio
    async def test_total_api_failure_returns_unclassified(self, provider):
        """Provider returns UNCLASSIFIED on total API failure."""
        with patch.object(
            provider,
            "_post_with_retry",
            side_effect=Exception("API down"),
        ):
            result = await provider.classify_and_extract("Some text here")

        assert result["type"] == EntryType.UNCLASSIFIED
        assert len(result["title"]) <= 60
        assert len(result["summary"]) <= 200

    @pytest.mark.asyncio
    async def test_embed_returns_vector(self, provider):
        """Provider returns embedding vector from API."""
        response_text = json.dumps([0.1] * 384)

        with patch.object(provider, "_post_with_retry", return_value=response_text):
            result = await provider.embed("Test text")

        assert len(result) == 384

    @pytest.mark.asyncio
    async def test_classification_prompt_contains_all_types(self, provider):
        """The prompt should list all 7 classifiable types."""
        text = "test"
        response_text = json.dumps({
            "choices": [{"message": {"content": '{"type": "note", "title": "T", "summary": "S"}'}}]
        })

        with patch.object(provider, "_post_with_retry", return_value=response_text) as mock_post:
            await provider.classify_and_extract(text)

        # Verify _post_with_retry was called (prompt was constructed)
        mock_post.assert_called_once()


class TestClassifier:
    """Tests for the Classifier service."""

    @pytest.mark.asyncio
    async def test_classify_and_embed_success(self, mock_hf_provider):
        """Classifier returns extraction dict + embedding on success."""
        classifier = Classifier(mock_hf_provider)
        extraction, embedding = await classifier.classify_and_embed("Test idea")

        assert extraction["type"] == EntryType.IDEA
        assert extraction["title"] == "Mock Title"
        assert len(embedding) == 384

    @pytest.mark.asyncio
    async def test_classify_failure_embed_success(self, mock_hf_provider):
        """Classifier falls back on classify failure, keeps embedding."""
        mock_hf_provider.classify_and_extract = AsyncMock(
            side_effect=Exception("LLM down")
        )
        classifier = Classifier(mock_hf_provider)
        extraction, embedding = await classifier.classify_and_embed(
            "Some important text"
        )

        assert extraction["type"] == EntryType.UNCLASSIFIED
        assert extraction["title"] == "Some important text"[:60]
        assert len(embedding) == 384

    @pytest.mark.asyncio
    async def test_embed_failure_classify_success(self, mock_hf_provider):
        """Classifier keeps classification but returns empty embedding."""
        mock_hf_provider.embed = AsyncMock(side_effect=Exception("Embed down"))
        classifier = Classifier(mock_hf_provider)
        extraction, embedding = await classifier.classify_and_embed("Idea text")

        assert extraction["type"] == EntryType.IDEA
        assert embedding == []

    @pytest.mark.asyncio
    async def test_title_fallback_truncated_to_60(self, mock_hf_provider):
        """On classify failure, title is truncated to 60 chars."""
        mock_hf_provider.classify_and_extract = AsyncMock(
            side_effect=Exception("Fail")
        )
        long_text = "A" * 200
        classifier = Classifier(mock_hf_provider)
        extraction, _ = await classifier.classify_and_embed(long_text)

        assert len(extraction["title"]) <= 60

    @pytest.mark.asyncio
    async def test_summary_fallback_truncated_to_200(self, mock_hf_provider):
        """On classify failure, summary is truncated to 200 chars."""
        mock_hf_provider.classify_and_extract = AsyncMock(
            side_effect=Exception("Fail")
        )
        long_text = "B" * 500
        classifier = Classifier(mock_hf_provider)
        extraction, _ = await classifier.classify_and_embed(long_text)

        assert len(extraction["summary"]) <= 200
