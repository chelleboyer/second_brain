"""Entry type enum and display configuration."""

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

# Valid types the LLM can classify into (excludes Unclassified error state)
CLASSIFIABLE_TYPES: list[EntryType] = [
    t for t in EntryType if t != EntryType.UNCLASSIFIED
]
