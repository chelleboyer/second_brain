"""Brain entry, entity, and relationship domain models."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.models.enums import (
    EntryType,
    EntityType,
    NoveltyVerdict,
    PARACategory,
    RelationshipType,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Core Entry ───────────────────────────────────────────────────


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

    # Phase 1: Enhanced classification fields
    para_category: PARACategory = PARACategory.RESOURCE
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extracted_entities: list[str] = Field(default_factory=list)
    novelty: NoveltyVerdict = NoveltyVerdict.NEW
    augments_entry_id: UUID | None = None  # If novelty == AUGMENT, which entry it augments


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

    # Phase 1: Enhanced fields
    para_category: PARACategory = PARACategory.RESOURCE
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extracted_entities: list[str] = Field(default_factory=list)


# ── Entity ───────────────────────────────────────────────────────


class Entity(BaseModel):
    """A named entity that spans multiple brain entries.

    Entities represent people, projects, technologies, concepts, or
    organizations that appear across captures. They are the primary
    mechanism for connecting related information.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str
    entity_type: EntityType
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    entry_count: int = 0  # Denormalized count of linked entries
    embedding_vector_id: str | None = None


class EntityMention(BaseModel):
    """Junction record linking an entity to a brain entry."""

    id: UUID = Field(default_factory=uuid4)
    entity_id: UUID
    entry_id: UUID
    mention_text: str  # The actual text that matched the entity
    created_at: datetime = Field(default_factory=_utcnow)


class EntitySummary(BaseModel):
    """Progressive summary for an entity — synthesized from all linked entries.

    Tracks the entry_count at the time of summarization so we know
    when the summary is stale and needs incremental update.
    """

    id: UUID = Field(default_factory=uuid4)
    entity_id: UUID
    summary_text: str = ""
    entry_count_at_summary: int = 0  # Entity entry_count when this was generated
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


# ── Relationship ─────────────────────────────────────────────────


class EntryRelationship(BaseModel):
    """A typed, directional link between two brain entries.

    source_entry_id --[relationship_type]--> target_entry_id
    Example: "Idea A" --[evolves]--> "Decision B"
    """

    id: UUID = Field(default_factory=uuid4)
    source_entry_id: UUID
    target_entry_id: UUID
    relationship_type: RelationshipType
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=_utcnow)
    reason: str = ""  # Why the system linked these


# ── Search & Classification Results ─────────────────────────────


class SearchResult(BaseModel):
    """A search result with score and source information."""

    entry: BrainEntry
    score: float
    source: Literal["vector", "keyword", "both", "entity", "graph"]


class ClassificationResult(BaseModel):
    """Structured output from the enhanced classifier.

    Carries everything the pipeline needs to decide how to store,
    link, and organize an incoming message.
    """

    entry_type: EntryType
    title: str
    summary: str
    para_category: PARACategory = PARACategory.RESOURCE
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    entities: list[dict] = Field(default_factory=list)
    # Each entity dict: {"name": str, "type": EntityType value str}
    project: str | None = None
    action_items: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
