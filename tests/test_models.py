"""Tests for Pydantic models and enums."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.models.brain_entry import BrainEntry, BrainEntryCreate, SearchResult
from src.models.enums import CLASSIFIABLE_TYPES, TYPE_DISPLAY, EntryType


class TestEntryType:
    """Tests for the EntryType enum."""

    def test_enum_has_eight_values(self):
        assert len(EntryType) == 8

    def test_all_type_values(self):
        expected = {
            "idea", "task", "decision", "risk",
            "arch_note", "strategy", "note", "unclassified",
        }
        assert {t.value for t in EntryType} == expected

    def test_type_display_maps_all_types(self):
        for entry_type in EntryType:
            assert entry_type in TYPE_DISPLAY
            display = TYPE_DISPLAY[entry_type]
            assert "emoji" in display
            assert "color" in display
            assert "label" in display

    def test_classifiable_types_excludes_unclassified(self):
        assert EntryType.UNCLASSIFIED not in CLASSIFIABLE_TYPES
        assert len(CLASSIFIABLE_TYPES) == 7


class TestBrainEntry:
    """Tests for the BrainEntry model."""

    def test_creates_with_valid_fields(self):
        entry = BrainEntry(
            type=EntryType.IDEA,
            title="Test",
            summary="Test summary",
            raw_content="Raw text",
            author_id="U123",
            author_name="Alice",
        )
        assert entry.type == EntryType.IDEA
        assert entry.title == "Test"
        assert entry.id is not None
        assert entry.created_at is not None

    def test_defaults(self):
        entry = BrainEntry(
            type=EntryType.NOTE,
            title="T",
            summary="S",
            raw_content="R",
            author_id="U1",
            author_name="A",
        )
        assert entry.project is None
        assert entry.tags == []
        assert entry.embedding_vector_id is None
        assert entry.slack_ts is None
        assert entry.slack_permalink is None
        assert entry.thread_ts is None
        assert entry.reply_count == 0
        assert entry.archived_at is None
        assert entry.source == "slack"

    def test_rejects_missing_required_fields(self):
        with pytest.raises(ValidationError):
            BrainEntry(type=EntryType.IDEA)  # Missing title, summary, etc.

    def test_slack_ts_optional_for_manual_captures(self):
        entry = BrainEntry(
            type=EntryType.IDEA,
            title="Manual thought",
            summary="Captured manually",
            raw_content="Text",
            slack_ts=None,
            slack_permalink=None,
            author_id="manual",
            author_name="Michelle",
            source="manual",
        )
        assert entry.slack_ts is None
        assert entry.source == "manual"

    def test_archived_at_defaults_to_none(self):
        entry = BrainEntry(
            type=EntryType.TASK,
            title="T",
            summary="S",
            raw_content="R",
            author_id="U",
            author_name="N",
        )
        assert entry.archived_at is None

    def test_source_literal_validation(self):
        with pytest.raises(ValidationError):
            BrainEntry(
                type=EntryType.IDEA,
                title="T",
                summary="S",
                raw_content="R",
                author_id="U",
                author_name="N",
                source="invalid",
            )


class TestBrainEntryCreate:
    """Tests for the BrainEntryCreate input model."""

    def test_creates_without_id_and_created_at(self):
        create = BrainEntryCreate(
            type=EntryType.DECISION,
            title="T",
            summary="S",
            raw_content="R",
            author_id="U",
            author_name="N",
        )
        assert not hasattr(create, "id")
        assert not hasattr(create, "created_at")
        assert create.type == EntryType.DECISION


class TestSearchResult:
    """Tests for the SearchResult model."""

    def test_validates_source_literal(self):
        entry = BrainEntry(
            type=EntryType.IDEA,
            title="T",
            summary="S",
            raw_content="R",
            author_id="U",
            author_name="N",
        )
        result = SearchResult(entry=entry, score=0.85, source="vector")
        assert result.source == "vector"

        result2 = SearchResult(entry=entry, score=0.9, source="both")
        assert result2.source == "both"

    def test_rejects_invalid_source(self):
        entry = BrainEntry(
            type=EntryType.IDEA,
            title="T",
            summary="S",
            raw_content="R",
            author_id="U",
            author_name="N",
        )
        with pytest.raises(ValidationError):
            SearchResult(entry=entry, score=0.5, source="unknown")
