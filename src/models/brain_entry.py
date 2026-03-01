"""Brain entry domain models."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.models.enums import EntryType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class BrainEntry(BaseModel):
    """Core domain model for a captured brain entry."""

    id: UUID = Field(default_factory=uuid4)
    type: EntryType
    title: str
    summary: str
    raw_content: str
    created_at: datetime = Field(default_factory=_utcnow)
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    embedding_vector_id: str | None = None
    slack_ts: str | None = None  # Unique Slack dedup key — None for manual captures
    slack_permalink: str | None = None  # None for manual captures
    author_id: str
    author_name: str
    thread_ts: str | None = None
    reply_count: int = 0
    archived_at: datetime | None = None
    source: Literal["slack", "manual"] = "slack"


class BrainEntryCreate(BaseModel):
    """Input model for creating a brain entry (without id/created_at)."""

    type: EntryType
    title: str
    summary: str
    raw_content: str
    project: str | None = None
    tags: list[str] = Field(default_factory=list)
    slack_ts: str | None = None
    slack_permalink: str | None = None
    author_id: str
    author_name: str
    thread_ts: str | None = None
    reply_count: int = 0
    source: Literal["slack", "manual"] = "slack"


class SearchResult(BaseModel):
    """A search result with score and source information."""

    entry: BrainEntry
    score: float
    source: Literal["vector", "keyword", "both"]
