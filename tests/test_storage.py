"""Tests for storage layer — database and repository."""

from datetime import datetime, timezone

import pytest

from src.models.brain_entry import BrainEntry
from src.models.enums import EntryType
from tests.conftest import make_entry


class TestRepository:
    """Tests for BrainEntryRepository CRUD operations."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_by_id(self, repository):
        """Save an entry and retrieve it by ID."""
        entry = make_entry(type=EntryType.IDEA, title="Save Test")
        saved = await repository.save(entry)

        retrieved = await repository.get_by_id(entry.id)
        assert retrieved is not None
        assert retrieved.id == entry.id
        assert retrieved.title == "Save Test"
        assert retrieved.type == EntryType.IDEA

    @pytest.mark.asyncio
    async def test_duplicate_slack_ts_ignored(self, repository):
        """Saving a duplicate slack_ts is silently ignored."""
        entry1 = make_entry(slack_ts="dup.123", title="First")
        entry2 = make_entry(slack_ts="dup.123", title="Second")

        await repository.save(entry1)
        await repository.save(entry2)

        # Should still have only the first entry
        result = await repository.get_by_id(entry1.id)
        assert result is not None
        assert result.title == "First"

    @pytest.mark.asyncio
    async def test_get_recent_returns_newest_first(self, repository):
        """Recent entries are returned newest first."""
        e1 = make_entry(
            title="Old",
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        )
        e2 = make_entry(
            title="New",
            created_at=datetime(2025, 6, 1, tzinfo=timezone.utc),
        )
        await repository.save(e1)
        await repository.save(e2)

        recent = await repository.get_recent(limit=10)
        assert len(recent) == 2
        assert recent[0].title == "New"
        assert recent[1].title == "Old"

    @pytest.mark.asyncio
    async def test_get_by_type_filters_correctly(self, repository):
        """Filtering by type returns only matching entries."""
        e1 = make_entry(type=EntryType.IDEA, title="An Idea")
        e2 = make_entry(type=EntryType.TASK, title="A Task")
        e3 = make_entry(type=EntryType.IDEA, title="Another Idea")
        await repository.save(e1)
        await repository.save(e2)
        await repository.save(e3)

        ideas = await repository.get_by_type(EntryType.IDEA)
        assert len(ideas) == 2
        assert all(e.type == EntryType.IDEA for e in ideas)

    @pytest.mark.asyncio
    async def test_keyword_search_finds_matching_entries(self, repository):
        """FTS5 keyword search finds entries by content."""
        entry = make_entry(
            title="Architecture Review",
            summary="Reviewing the system architecture",
            raw_content="We need to review the architecture of our system",
        )
        await repository.save(entry)

        results = await repository.search_keyword("architecture")
        assert len(results) >= 1
        found = any(e.title == "Architecture Review" for e, _ in results)
        assert found

    @pytest.mark.asyncio
    async def test_keyword_search_returns_ranked_results(self, repository):
        """FTS5 search results include relevance scores."""
        e1 = make_entry(
            title="Python Guide",
            summary="Python programming guide",
            raw_content="Python is great for programming",
        )
        e2 = make_entry(
            title="Java Guide",
            summary="Java programming",
            raw_content="Java is also a programming language",
        )
        await repository.save(e1)
        await repository.save(e2)

        results = await repository.search_keyword("Python")
        assert len(results) >= 1
        # Results should have scores
        for entry, score in results:
            assert isinstance(score, float)

    @pytest.mark.asyncio
    async def test_get_digest_returns_correct_counts(self, repository):
        """Digest returns correct counts by type for a given date."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        e1 = make_entry(type=EntryType.IDEA)
        e2 = make_entry(type=EntryType.IDEA)
        e3 = make_entry(type=EntryType.TASK)
        await repository.save(e1)
        await repository.save(e2)
        await repository.save(e3)

        digest = await repository.get_digest(today)
        assert digest.get("idea", 0) == 2
        assert digest.get("task", 0) == 1

    @pytest.mark.asyncio
    async def test_last_processed_ts_roundtrips(self, repository):
        """Last processed timestamp can be set and retrieved."""
        assert await repository.get_last_processed_ts() is None

        await repository.set_last_processed_ts("1234567890.123456")
        result = await repository.get_last_processed_ts()
        assert result == "1234567890.123456"

        await repository.set_last_processed_ts("1234567899.000000")
        result = await repository.get_last_processed_ts()
        assert result == "1234567899.000000"

    @pytest.mark.asyncio
    async def test_entry_exists(self, repository):
        """entry_exists returns True for saved entries."""
        entry = make_entry(slack_ts="exists.123")
        await repository.save(entry)

        assert await repository.entry_exists("exists.123") is True
        assert await repository.entry_exists("nope.999") is False

    @pytest.mark.asyncio
    async def test_archive_sets_archived_at(self, repository):
        """Archiving an entry sets the archived_at timestamp."""
        entry = make_entry(title="To Archive")
        await repository.save(entry)

        archived = await repository.archive(entry.id)
        assert archived is not None
        assert archived.archived_at is not None

    @pytest.mark.asyncio
    async def test_unarchive_clears_archived_at(self, repository):
        """Unarchiving an entry clears the archived_at timestamp."""
        entry = make_entry(title="To Unarchive")
        await repository.save(entry)
        await repository.archive(entry.id)

        unarchived = await repository.unarchive(entry.id)
        assert unarchived is not None
        assert unarchived.archived_at is None

    @pytest.mark.asyncio
    async def test_get_recent_excludes_archived(self, repository):
        """get_recent excludes archived entries by default."""
        e1 = make_entry(title="Active")
        e2 = make_entry(title="Archived")
        await repository.save(e1)
        await repository.save(e2)
        await repository.archive(e2.id)

        recent = await repository.get_recent(limit=50)
        assert len(recent) == 1
        assert recent[0].title == "Active"

    @pytest.mark.asyncio
    async def test_get_recent_includes_archived_when_requested(self, repository):
        """get_recent includes archived entries when flag is set."""
        e1 = make_entry(title="Active")
        e2 = make_entry(title="Archived")
        await repository.save(e1)
        await repository.save(e2)
        await repository.archive(e2.id)

        all_entries = await repository.get_recent(limit=50, include_archived=True)
        assert len(all_entries) == 2

    @pytest.mark.asyncio
    async def test_get_archived(self, repository):
        """get_archived returns only archived entries."""
        e1 = make_entry(title="Active")
        e2 = make_entry(title="Archived")
        await repository.save(e1)
        await repository.save(e2)
        await repository.archive(e2.id)

        archived = await repository.get_archived()
        assert len(archived) == 1
        assert archived[0].title == "Archived"

    @pytest.mark.asyncio
    async def test_delete_removes_entry(self, repository):
        """delete permanently removes an entry."""
        entry = make_entry(title="To Delete")
        await repository.save(entry)

        deleted = await repository.delete(entry.id)
        assert deleted is True
        assert await repository.get_by_id(entry.id) is None

    @pytest.mark.asyncio
    async def test_update_changes_fields(self, repository):
        """update modifies specified fields only."""
        entry = make_entry(title="Original", summary="Old summary", type=EntryType.NOTE)
        await repository.save(entry)

        updated = await repository.update(
            entry.id,
            title="Updated Title",
            summary="New summary",
            entry_type=EntryType.IDEA,
        )
        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.summary == "New summary"
        assert updated.type == EntryType.IDEA

    @pytest.mark.asyncio
    async def test_count_all(self, repository):
        """count_all returns correct active/archived/total counts."""
        e1 = make_entry(title="Active 1")
        e2 = make_entry(title="Active 2")
        e3 = make_entry(title="Archived")
        await repository.save(e1)
        await repository.save(e2)
        await repository.save(e3)
        await repository.archive(e3.id)

        counts = await repository.count_all()
        assert counts["total"] == 3
        assert counts["active"] == 2
        assert counts["archived"] == 1
