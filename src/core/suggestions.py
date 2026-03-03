"""Smart suggestions engine — context-aware recommendations on capture."""

from collections import defaultdict
from datetime import datetime, timezone, timedelta
from uuid import UUID

import structlog

from src.core.entity_resolution import EntityRepository
from src.core.graph import GraphService
from src.models.brain_entry import BrainEntry, Entity
from src.models.enums import EntryType, EntityType, RelationshipType
from src.storage.repository import BrainEntryRepository
from src.storage.strategy_repository import StrategyRepository

log = structlog.get_logger(__name__)

# Type-based suggestion rules: when you capture type X, look for type Y
TYPE_SUGGESTION_RULES: dict[EntryType, list[dict]] = {
    EntryType.RISK: [
        {
            "look_for": [EntryType.DECISION, EntryType.STRATEGY],
            "message": "Related decisions and strategies that may address this risk:",
            "relationship": RelationshipType.RELATED_TO,
        },
    ],
    EntryType.TASK: [
        {
            "look_for": [EntryType.IDEA, EntryType.DECISION],
            "message": "Ideas and decisions this task may implement:",
            "relationship": RelationshipType.IMPLEMENTS,
        },
    ],
    EntryType.DECISION: [
        {
            "look_for": [EntryType.RISK, EntryType.STRATEGY],
            "message": "Risks and strategies related to this decision:",
            "relationship": RelationshipType.RELATED_TO,
        },
        {
            "look_for": [EntryType.IDEA],
            "message": "Ideas this decision evolves from:",
            "relationship": RelationshipType.EVOLVES,
        },
    ],
    EntryType.STRATEGY: [
        {
            "look_for": [EntryType.DECISION, EntryType.TASK],
            "message": "Decisions and tasks that implement this strategy:",
            "relationship": RelationshipType.IMPLEMENTS,
        },
    ],
    EntryType.IDEA: [
        {
            "look_for": [EntryType.DECISION, EntryType.TASK],
            "message": "Decisions and tasks that may relate to this idea:",
            "relationship": RelationshipType.RELATED_TO,
        },
    ],
    EntryType.ARCH_NOTE: [
        {
            "look_for": [EntryType.DECISION, EntryType.RISK],
            "message": "Decisions and risks related to this architecture note:",
            "relationship": RelationshipType.RELATED_TO,
        },
    ],
}


class Suggestion:
    """A single actionable suggestion."""

    def __init__(
        self,
        suggestion_type: str,
        message: str,
        related_entries: list[BrainEntry] | None = None,
        related_entities: list[Entity] | None = None,
        action: str | None = None,
    ) -> None:
        self.suggestion_type = suggestion_type  # "type_link", "proactive", "summary"
        self.message = message
        self.related_entries = related_entries or []
        self.related_entities = related_entities or []
        self.action = action  # Optional action prompt for the user

    def to_dict(self) -> dict:
        """Serialize for API/template consumption."""
        return {
            "suggestion_type": self.suggestion_type,
            "message": self.message,
            "related_entries": [
                {
                    "id": str(e.id),
                    "title": e.title,
                    "type": e.type.value,
                    "summary": e.summary,
                }
                for e in self.related_entries
            ],
            "related_entities": [
                {
                    "id": str(e.id),
                    "name": e.name,
                    "type": e.entity_type.value,
                }
                for e in self.related_entities
            ],
            "action": self.action,
        }


class SuggestionEngine:
    """Generates smart suggestions based on captured content.

    Supports:
    - Type-based linking: when a risk is captured → surface related decisions
    - Proactive prompts: "You captured 3 things about X this week — want a summary?"
    - Entity-based suggestions: surface entries sharing entities with the new capture
    - Initiative promotion: suggest promoting unlinked project entities to initiatives
    """

    def __init__(
        self,
        entity_repo: EntityRepository,
        entry_repo: BrainEntryRepository,
        graph_service: GraphService,
        strategy_repo: StrategyRepository | None = None,
    ) -> None:
        self.entity_repo = entity_repo
        self.entry_repo = entry_repo
        self.graph_service = graph_service
        self.strategy_repo = strategy_repo

    async def generate_suggestions(
        self, entry: BrainEntry, resolved_entities: list[Entity] | None = None
    ) -> list[Suggestion]:
        """Generate all applicable suggestions for a newly captured entry.

        Args:
            entry: The just-captured brain entry
            resolved_entities: Entities resolved during capture (if available)

        Returns:
            List of Suggestion objects, ordered by relevance
        """
        suggestions: list[Suggestion] = []

        # 1. Type-based suggestions (via shared entities)
        type_suggestions = await self._type_based_suggestions(
            entry, resolved_entities or []
        )
        suggestions.extend(type_suggestions)

        # 2. Proactive activity suggestions
        proactive = await self._proactive_suggestions(entry, resolved_entities or [])
        suggestions.extend(proactive)

        # 3. Entity-based related content
        entity_suggestions = await self._entity_based_suggestions(
            entry, resolved_entities or []
        )
        suggestions.extend(entity_suggestions)

        # 4. Initiative promotion suggestions
        initiative_suggestions = await self._initiative_promotion_suggestions(
            entry, resolved_entities or []
        )
        suggestions.extend(initiative_suggestions)

        log.info(
            "suggestions_generated",
            entry_id=str(entry.id),
            entry_type=entry.type.value,
            count=len(suggestions),
        )

        return suggestions

    # ── Type-Based Suggestions ───────────────────────────────────

    async def _type_based_suggestions(
        self, entry: BrainEntry, entities: list[Entity]
    ) -> list[Suggestion]:
        """Find entries of complementary types that share entities.

        Example: Risk captured with entity "ProjectX" → find Decisions
        about "ProjectX".
        """
        rules = TYPE_SUGGESTION_RULES.get(entry.type, [])
        if not rules or not entities:
            return []

        suggestions: list[Suggestion] = []

        for rule in rules:
            related_entries: list[BrainEntry] = []

            # Find entries sharing entities with the target types
            for entity in entities:
                entry_ids = await self.entity_repo.get_entries_for_entity(entity.id)
                for entry_id_str in entry_ids:
                    if entry_id_str == str(entry.id):
                        continue
                    related = await self.entry_repo.get_by_id(UUID(entry_id_str))
                    if (
                        related
                        and related.type in rule["look_for"]
                        and related.archived_at is None
                        and related.id not in [e.id for e in related_entries]
                    ):
                        related_entries.append(related)

            if related_entries:
                # Sort by relevance (newer first, limit to top 5)
                related_entries.sort(key=lambda e: e.created_at, reverse=True)
                suggestions.append(
                    Suggestion(
                        suggestion_type="type_link",
                        message=rule["message"],
                        related_entries=related_entries[:5],
                    )
                )

        return suggestions

    # ── Proactive Suggestions ────────────────────────────────────

    async def _proactive_suggestions(
        self, entry: BrainEntry, entities: list[Entity]
    ) -> list[Suggestion]:
        """Generate proactive suggestions based on recent activity patterns.

        Triggers:
        - "You've captured N things about EntityX this week — want a summary?"
        - "EntityX has been mentioned in multiple types — evolving from idea to decision?"
        """
        suggestions: list[Suggestion] = []
        one_week_ago = datetime.now(timezone.utc) - timedelta(days=7)

        for entity in entities:
            if entity.entry_count < 3:
                continue

            # Count recent entries mentioning this entity
            entry_ids = await self.entity_repo.get_entries_for_entity(entity.id)
            recent_count = 0
            recent_entries: list[BrainEntry] = []

            for entry_id_str in entry_ids:
                related = await self.entry_repo.get_by_id(UUID(entry_id_str))
                if related and related.created_at >= one_week_ago:
                    recent_count += 1
                    recent_entries.append(related)

            if recent_count >= 3:
                suggestions.append(
                    Suggestion(
                        suggestion_type="proactive",
                        message=(
                            f"You've captured {recent_count} things about "
                            f'"{entity.name}" this week — want a summary?'
                        ),
                        related_entries=recent_entries[:5],
                        related_entities=[entity],
                        action=f"summarize_entity:{entity.id}",
                    )
                )

            # Check for type evolution (idea → decision pattern)
            if len(recent_entries) >= 2:
                types_seen = {e.type for e in recent_entries}
                if EntryType.IDEA in types_seen and EntryType.DECISION in types_seen:
                    suggestions.append(
                        Suggestion(
                            suggestion_type="proactive",
                            message=(
                                f'"{entity.name}" is evolving: you have both ideas '
                                f"and decisions. Consider linking them."
                            ),
                            related_entries=[
                                e
                                for e in recent_entries
                                if e.type in (EntryType.IDEA, EntryType.DECISION)
                            ][:4],
                            related_entities=[entity],
                        )
                    )

        return suggestions

    # ── Entity-Based Suggestions ─────────────────────────────────

    async def _entity_based_suggestions(
        self, entry: BrainEntry, entities: list[Entity]
    ) -> list[Suggestion]:
        """Find related entries through entity co-occurrence.

        Only suggests entries not already surfaced by type-based suggestions.
        Limited to entries sharing 2+ entities with the new capture.
        """
        if len(entities) < 2:
            return []

        # Count co-occurrence of entries across entities
        entry_overlap: dict[str, tuple[int, BrainEntry | None]] = defaultdict(
            lambda: (0, None)
        )

        for entity in entities:
            entry_ids = await self.entity_repo.get_entries_for_entity(entity.id)
            for entry_id_str in entry_ids:
                if entry_id_str == str(entry.id):
                    continue
                count, existing = entry_overlap.get(entry_id_str, (0, None))
                if existing is None:
                    existing = await self.entry_repo.get_by_id(UUID(entry_id_str))
                entry_overlap[entry_id_str] = (count + 1, existing)

        # Filter to entries sharing 2+ entities
        related: list[BrainEntry] = []
        for entry_id_str, (count, related_entry) in entry_overlap.items():
            if count >= 2 and related_entry and related_entry.archived_at is None:
                related.append(related_entry)

        if related:
            related.sort(key=lambda e: e.created_at, reverse=True)
            shared_names = ", ".join(e.name for e in entities[:3])
            return [
                Suggestion(
                    suggestion_type="entity_overlap",
                    message=f"Entries sharing multiple entities ({shared_names}):",
                    related_entries=related[:5],
                    related_entities=entities,
                )
            ]

        return []

    # ── Initiative Promotion Suggestions ─────────────────────────

    async def _initiative_promotion_suggestions(
        self, entry: BrainEntry, entities: list[Entity]
    ) -> list[Suggestion]:
        """Suggest promoting project entities that aren't tracked as initiatives.

        When a captured entry mentions a project (via project field or
        project-type entities) that doesn't match any existing initiative,
        suggest the user promote it to the strategy tab.
        """
        if not self.strategy_repo:
            return []

        suggestions: list[Suggestion] = []

        # Collect project names to check
        project_names: list[str] = []
        if entry.project:
            project_names.append(entry.project)
        for entity in entities:
            if (
                entity.entity_type == EntityType.PROJECT
                and entity.name not in project_names
            ):
                project_names.append(entity.name)

        for name in project_names:
            matches = await self.strategy_repo.find_initiatives_by_title(name)
            if not matches:
                suggestions.append(
                    Suggestion(
                        suggestion_type="promote_initiative",
                        message=(
                            f'"{name}" isn\'t tracked as a strategic initiative yet '
                            f"— promote it to run the optionality engine on it?"
                        ),
                        related_entities=[
                            e for e in entities if e.name.lower() == name.lower()
                        ],
                        action=f"promote_to_initiative:{name}",
                    )
                )

        return suggestions

    # ── Utility ──────────────────────────────────────────────────

    async def get_suggestions_for_entry(
        self, entry_id: UUID
    ) -> list[Suggestion]:
        """Generate suggestions for an existing entry (on-demand).

        Useful for the dashboard to show suggestions when viewing an entry.
        """
        entry = await self.entry_repo.get_by_id(entry_id)
        if not entry:
            return []

        # Resolve entities from the entry's extracted_entities field
        entities: list[Entity] = []
        for entity_name in entry.extracted_entities:
            found = await self.entity_repo.search_entities_by_name(entity_name)
            if found:
                entities.append(found[0])

        return await self.generate_suggestions(entry, entities)
