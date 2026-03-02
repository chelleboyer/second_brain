"""Entry type, PARA category, relationship, and novelty enums + display config."""

from enum import Enum


class EntryType(str, Enum):
    """Classification types for brain entries."""

    IDEA = "idea"
    TASK = "task"
    DECISION = "decision"
    RISK = "risk"
    ARCH_NOTE = "arch_note"
    STRATEGY = "strategy"
    NOTE = "note"
    UNCLASSIFIED = "unclassified"


class PARACategory(str, Enum):
    """PARA organizational categories (Tiago Forte)."""

    PROJECT = "project"   # Active efforts with a deadline/goal
    AREA = "area"         # Ongoing responsibilities (no end date)
    RESOURCE = "resource" # Topics of interest / reference material
    ARCHIVE = "archive"   # Inactive items from the above three


class RelationshipType(str, Enum):
    """Types of relationships between brain entries."""

    SUPPORTS = "supports"         # A reinforces/validates B
    CONTRADICTS = "contradicts"   # A conflicts with B
    EVOLVES = "evolves"           # A is an updated version of B
    IMPLEMENTS = "implements"     # A puts B into action
    BLOCKS = "blocks"             # A prevents progress on B
    RELATED_TO = "related_to"    # General topical connection


class NoveltyVerdict(str, Enum):
    """Outcome of novelty detection for incoming content."""

    NEW = "new"           # Genuinely new knowledge
    AUGMENT = "augment"   # Adds to / updates existing entry
    DUPLICATE = "duplicate"  # Already captured — skip


class EntityType(str, Enum):
    """Types of extracted entities."""

    PROJECT = "project"
    PERSON = "person"
    TECHNOLOGY = "technology"
    CONCEPT = "concept"
    ORGANIZATION = "organization"


# Display configuration: emoji, color, and label for each type
TYPE_DISPLAY: dict[EntryType, dict[str, str]] = {
    EntryType.IDEA: {"emoji": "💡", "color": "blue", "label": "Idea"},
    EntryType.TASK: {"emoji": "✅", "color": "green", "label": "Task"},
    EntryType.DECISION: {"emoji": "⚖️", "color": "purple", "label": "Decision"},
    EntryType.RISK: {"emoji": "⚠️", "color": "red", "label": "Risk"},
    EntryType.ARCH_NOTE: {"emoji": "🏗️", "color": "gray", "label": "Arch Note"},
    EntryType.STRATEGY: {"emoji": "🎯", "color": "gold", "label": "Strategy"},
    EntryType.NOTE: {"emoji": "📝", "color": "teal", "label": "Note"},
    EntryType.UNCLASSIFIED: {"emoji": "❓", "color": "yellow", "label": "Unclassified"},
}

PARA_DISPLAY: dict[PARACategory, dict[str, str]] = {
    PARACategory.PROJECT: {"emoji": "🚀", "color": "indigo", "label": "Project"},
    PARACategory.AREA: {"emoji": "🔄", "color": "emerald", "label": "Area"},
    PARACategory.RESOURCE: {"emoji": "📚", "color": "amber", "label": "Resource"},
    PARACategory.ARCHIVE: {"emoji": "🗄️", "color": "slate", "label": "Archive"},
}

ENTITY_DISPLAY: dict[EntityType, dict[str, str]] = {
    EntityType.PROJECT: {"emoji": "🚀", "color": "indigo", "label": "Project"},
    EntityType.PERSON: {"emoji": "👤", "color": "sky", "label": "Person"},
    EntityType.TECHNOLOGY: {"emoji": "⚙️", "color": "violet", "label": "Technology"},
    EntityType.CONCEPT: {"emoji": "🧠", "color": "rose", "label": "Concept"},
    EntityType.ORGANIZATION: {"emoji": "🏢", "color": "orange", "label": "Organization"},
}

# Valid types the LLM can classify into (excludes Unclassified error state)
CLASSIFIABLE_TYPES: list[EntryType] = [
    t for t in EntryType if t != EntryType.UNCLASSIFIED
]
