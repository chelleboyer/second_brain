"""Entry type, PARA category, relationship, novelty, and strategy enums + display config."""

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


class VisibilityLevel(str, Enum):
    """Strategic visibility level for initiatives and assets."""

    HIDDEN = "hidden"       # Low signal — internal/unknown
    LOCAL = "local"         # Team-level signal
    EXECUTIVE = "executive" # Org-level signal
    MARKET = "market"       # External/public signal


class InitiativeType(str, Enum):
    """Whether an initiative is scored or mandatory."""

    SCORED = "scored"       # Evaluated via 5-question framework
    MANDATORY = "mandatory" # Must-do — value comes from relationships


class InitiativeCategory(str, Enum):
    """Scoring tier for initiatives based on strategic alignment."""

    MAINTENANCE = "maintenance"   # Score < 12 — keep the lights on
    SUPPORTIVE = "supportive"     # Score 12–17 — useful but not game-changing
    STRATEGIC = "strategic"       # Score 18+ — high-leverage strategic move


class AssetCategory(str, Enum):
    """Type of strategic asset."""

    REPUTATION = "reputation"     # Public-facing credibility asset
    OPTIONALITY = "optionality"   # Portable, market-relevant asset


# Display configuration: emoji, color, and label for each type
TYPE_DISPLAY: dict[EntryType, dict[str, str]] = {
    EntryType.IDEA: {"emoji": "💡", "color": "blue", "label": "Idea"},
    EntryType.TASK: {"emoji": "✅", "color": "green", "label": "Task"},
    EntryType.DECISION: {"emoji": "⚖️", "color": "purple", "label": "Decision"},
    EntryType.RISK: {"emoji": "⚠️", "color": "red", "label": "Risk"},
    EntryType.ARCH_NOTE: {"emoji": "🏗️", "color": "gray", "label": "Arch Note"},
    EntryType.STRATEGY: {"emoji": "🎯", "color": "gold", "label": "Goal"},
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

VISIBILITY_DISPLAY: dict[VisibilityLevel, dict[str, str]] = {
    VisibilityLevel.HIDDEN: {"emoji": "🔒", "color": "gray", "label": "Hidden"},
    VisibilityLevel.LOCAL: {"emoji": "👥", "color": "teal", "label": "Local"},
    VisibilityLevel.EXECUTIVE: {"emoji": "🏛️", "color": "purple", "label": "Executive"},
    VisibilityLevel.MARKET: {"emoji": "🌐", "color": "gold", "label": "Market"},
}

INITIATIVE_TYPE_DISPLAY: dict[InitiativeType, dict[str, str]] = {
    InitiativeType.SCORED: {"emoji": "📊", "color": "blue", "label": "Scored"},
    InitiativeType.MANDATORY: {"emoji": "📌", "color": "red", "label": "Mandatory"},
}

INITIATIVE_CATEGORY_DISPLAY: dict[InitiativeCategory, dict[str, str]] = {
    InitiativeCategory.MAINTENANCE: {"emoji": "🔧", "color": "gray", "label": "Maintenance"},
    InitiativeCategory.SUPPORTIVE: {"emoji": "🤝", "color": "blue", "label": "Supportive"},
    InitiativeCategory.STRATEGIC: {"emoji": "♟️", "color": "gold", "label": "Strategic"},
}

ASSET_CATEGORY_DISPLAY: dict[AssetCategory, dict[str, str]] = {
    AssetCategory.REPUTATION: {"emoji": "🏆", "color": "purple", "label": "Reputation"},
    AssetCategory.OPTIONALITY: {"emoji": "🚪", "color": "emerald", "label": "Optionality"},
}

# Valid types the LLM can classify into (excludes Unclassified error state)
CLASSIFIABLE_TYPES: list[EntryType] = [
    t for t in EntryType if t != EntryType.UNCLASSIFIED
]
