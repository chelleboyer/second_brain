"""Tests for Slack command handler — /brain slash commands."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.models.enums import EntryType, PARACategory, NoveltyVerdict
from src.slack.commands import SlackCommandHandler
from tests.conftest import make_entry


class TestSlackCommandHandler:
    """Tests for SlackCommandHandler routing and responses."""

    def _make_handler(self, **kwargs) -> SlackCommandHandler:
        """Create a handler with optional mock dependencies."""
        return SlackCommandHandler(**kwargs)

    @pytest.mark.asyncio
    async def test_empty_command_returns_help(self):
        handler = self._make_handler()
        result = await handler.handle("")
        assert result["response_type"] == "ephemeral"
        assert "Commands" in result["text"] or "help" in result["text"].lower()

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        handler = self._make_handler()
        result = await handler.handle("foobar")
        assert "Unknown command" in result["text"]
        assert result["response_type"] == "ephemeral"

    @pytest.mark.asyncio
    async def test_help_command(self):
        handler = self._make_handler()
        result = await handler.handle("help")
        assert "capture" in result["text"]
        assert "recall" in result["text"]
        assert "entity" in result["text"]

    @pytest.mark.asyncio
    async def test_capture_no_text(self):
        handler = self._make_handler(pipeline=MagicMock())
        result = await handler.handle("capture")
        assert "Usage" in result["text"]

    @pytest.mark.asyncio
    async def test_capture_no_pipeline(self):
        handler = self._make_handler(pipeline=None)
        result = await handler.handle("capture some text")
        assert "not available" in result["text"]

    @pytest.mark.asyncio
    async def test_capture_success(self):
        entry = make_entry(
            title="Test Capture",
            summary="A captured thought",
            confidence=0.85,
            extracted_entities=["FastAPI", "Python"],
            novelty=NoveltyVerdict.NEW,
            para_category=PARACategory.PROJECT,
        )
        pipeline = MagicMock()
        pipeline.capture_manual = AsyncMock(return_value=entry)

        handler = self._make_handler(pipeline=pipeline)
        result = await handler.handle("capture This is a test thought")

        assert result["response_type"] == "in_channel"
        assert "Test Capture" in result["text"]
        assert "FastAPI" in result["text"]
        assert "Python" in result["text"]

    @pytest.mark.asyncio
    async def test_capture_augment_indicator(self):
        entry = make_entry(
            title="Augment",
            summary="Sum",
            confidence=0.8,
            novelty=NoveltyVerdict.AUGMENT,
            para_category=PARACategory.AREA,
        )
        pipeline = MagicMock()
        pipeline.capture_manual = AsyncMock(return_value=entry)

        handler = self._make_handler(pipeline=pipeline)
        result = await handler.handle("capture Some augmenting text")
        assert "augments" in result["text"].lower() or "↗" in result["text"]

    @pytest.mark.asyncio
    async def test_recall_no_query(self):
        handler = self._make_handler(recall_service=MagicMock())
        result = await handler.handle("recall")
        assert "Usage" in result["text"]

    @pytest.mark.asyncio
    async def test_recall_no_service(self):
        handler = self._make_handler(recall_service=None)
        result = await handler.handle("recall some query")
        assert "not available" in result["text"]

    @pytest.mark.asyncio
    async def test_recall_no_results(self):
        from src.retrieval.recall import RecallResult

        recall_svc = MagicMock()
        recall_svc.recall_simple = AsyncMock(
            return_value=RecallResult(
                answer="No results", sources=[], search_results=[], confidence=0.0
            )
        )
        handler = self._make_handler(recall_service=recall_svc)
        result = await handler.handle("recall nonexistent topic")
        assert "No entries found" in result["text"]

    @pytest.mark.asyncio
    async def test_recall_with_results(self):
        from src.retrieval.recall import RecallResult
        from src.models.brain_entry import SearchResult

        entry = make_entry(title="Recall Match", summary="A matching entry")
        recall_svc = MagicMock()
        recall_svc.recall_simple = AsyncMock(
            return_value=RecallResult(
                answer="Found results",
                sources=[entry],
                search_results=[
                    SearchResult(entry=entry, score=0.85, source="vector")
                ],
                confidence=0.8,
            )
        )
        handler = self._make_handler(recall_service=recall_svc)
        result = await handler.handle("recall matching topic")
        assert result["response_type"] == "in_channel"
        assert "Recall Match" in result["text"]

    @pytest.mark.asyncio
    async def test_entity_no_name(self):
        handler = self._make_handler(entity_repo=MagicMock())
        result = await handler.handle("entity")
        assert "Usage" in result["text"]

    @pytest.mark.asyncio
    async def test_entity_no_repo(self):
        handler = self._make_handler(entity_repo=None)
        result = await handler.handle("entity FastAPI")
        assert "not available" in result["text"]

    @pytest.mark.asyncio
    async def test_entity_not_found(self):
        entity_repo = MagicMock()
        entity_repo.search_entities_by_name = AsyncMock(return_value=[])
        handler = self._make_handler(entity_repo=entity_repo)
        result = await handler.handle("entity NonExistent")
        assert "No entity found" in result["text"]

    @pytest.mark.asyncio
    async def test_entity_found(self):
        from datetime import datetime, timezone
        from src.models.enums import EntityType

        entity = MagicMock()
        entity.name = "FastAPI"
        entity.entity_type = EntityType.TECHNOLOGY
        entity.entry_count = 5
        entity.aliases = ["fastapi"]
        entity.description = "A web framework"
        entity.updated_at = datetime.now(timezone.utc)
        entity.id = uuid4()

        entity_repo = MagicMock()
        entity_repo.search_entities_by_name = AsyncMock(return_value=[entity])
        entity_repo.get_entries_for_entity = AsyncMock(return_value=["id1", "id2"])

        handler = self._make_handler(entity_repo=entity_repo)
        result = await handler.handle("entity FastAPI")
        assert result["response_type"] == "in_channel"
        assert "FastAPI" in result["text"]
        assert "5 linked entries" in result["text"]

    @pytest.mark.asyncio
    async def test_summarize_no_target(self):
        handler = self._make_handler(
            entity_repo=MagicMock(), summarization_service=MagicMock()
        )
        result = await handler.handle("summarize")
        assert "Usage" in result["text"]

    @pytest.mark.asyncio
    async def test_summarize_no_service(self):
        handler = self._make_handler(entity_repo=None, summarization_service=None)
        result = await handler.handle("summarize FastAPI")
        assert "not available" in result["text"]

    @pytest.mark.asyncio
    async def test_command_error_handling(self):
        """Errors in command handling should return an error message, not crash."""
        pipeline = MagicMock()
        pipeline.capture_manual = AsyncMock(
            side_effect=RuntimeError("DB down")
        )
        handler = self._make_handler(pipeline=pipeline)
        result = await handler.handle("capture some text")
        assert "went wrong" in result["text"].lower() or "Something" in result["text"]
        assert result["response_type"] == "ephemeral"
