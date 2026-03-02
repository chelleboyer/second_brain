"""Graph traversal service — backlinks, relationship chains, and depth-limited walks."""

from collections import defaultdict, deque
from uuid import UUID

import structlog

from src.core.entity_resolution import EntityRepository
from src.models.brain_entry import BrainEntry, Entity, EntryRelationship
from src.models.enums import EntityType, EntryType, RelationshipType
from src.storage.repository import BrainEntryRepository

log = structlog.get_logger(__name__)

# Maximum depth for graph walks to prevent runaway traversals
MAX_WALK_DEPTH = 5


class GraphService:
    """Knowledge graph traversal and query service.

    Provides:
    - Backlinks: "What else mentions this entity?"
    - Relationship chains: "Show path from Idea → Decision → Implementation"
    - Depth-limited graph walks: discover related content within N hops
    - Entity co-occurrence: find entities commonly mentioned together
    """

    def __init__(
        self,
        entity_repo: EntityRepository,
        entry_repo: BrainEntryRepository,
    ) -> None:
        self.entity_repo = entity_repo
        self.entry_repo = entry_repo

    # ── Backlinks ────────────────────────────────────────────────

    async def get_backlinks(self, entity_id: UUID) -> list[BrainEntry]:
        """Get all brain entries that mention a specific entity.

        This answers: "What else mentions this entity?"
        """
        entry_ids = await self.entity_repo.get_entries_for_entity(entity_id)
        entries: list[BrainEntry] = []
        for entry_id_str in entry_ids:
            entry = await self.entry_repo.get_by_id(UUID(entry_id_str))
            if entry and entry.archived_at is None:
                entries.append(entry)
        # Sort by created_at descending (newest first)
        entries.sort(key=lambda e: e.created_at, reverse=True)
        return entries

    async def get_entity_backlinks_summary(
        self, entity_id: UUID
    ) -> dict:
        """Get a summary of backlinks grouped by entry type.

        Returns:
            {
                "entity": Entity,
                "total_entries": int,
                "by_type": {EntryType: [BrainEntry, ...]},
                "entries": [BrainEntry, ...]
            }
        """
        entity = await self.entity_repo.get_entity_by_id(entity_id)
        if not entity:
            return {"entity": None, "total_entries": 0, "by_type": {}, "entries": []}

        entries = await self.get_backlinks(entity_id)
        by_type: dict[str, list[BrainEntry]] = defaultdict(list)
        for entry in entries:
            by_type[entry.type.value].append(entry)

        return {
            "entity": entity,
            "total_entries": len(entries),
            "by_type": dict(by_type),
            "entries": entries,
        }

    # ── Relationship Chain Traversal ─────────────────────────────

    async def find_relationship_chain(
        self,
        start_entry_id: UUID,
        target_types: list[RelationshipType] | None = None,
        max_depth: int = 3,
    ) -> list[list[dict]]:
        """Find relationship chains from a starting entry.

        Returns all paths from the start entry, following relationship edges,
        up to max_depth hops. Each path is a list of dicts:
        [{"entry": BrainEntry, "relationship": RelationshipType, "direction": "outgoing"|"incoming"}, ...]

        Args:
            start_entry_id: UUID of the starting entry
            target_types: Limit traversal to these relationship types (None = all)
            max_depth: Maximum chain length (capped at MAX_WALK_DEPTH)
        """
        max_depth = min(max_depth, MAX_WALK_DEPTH)
        chains: list[list[dict]] = []
        visited: set[str] = {str(start_entry_id)}

        start_entry = await self.entry_repo.get_by_id(start_entry_id)
        if not start_entry:
            return chains

        # BFS to find all paths
        # Each queue item: (current_entry_id, current_path)
        queue: deque[tuple[UUID, list[dict]]] = deque()
        queue.append((start_entry_id, [{"entry": start_entry, "relationship": None, "direction": "start"}]))

        while queue:
            current_id, path = queue.popleft()

            if len(path) > max_depth + 1:  # +1 for the start node
                continue

            rels = await self.entity_repo.get_relationships_for_entry(current_id)

            for rel in rels:
                # Determine direction and next entry
                if str(rel.source_entry_id) == str(current_id):
                    next_id = rel.target_entry_id
                    direction = "outgoing"
                else:
                    next_id = rel.source_entry_id
                    direction = "incoming"

                next_id_str = str(next_id)
                if next_id_str in visited:
                    continue

                # Filter by relationship type if specified
                if target_types and rel.relationship_type not in target_types:
                    continue

                next_entry = await self.entry_repo.get_by_id(next_id)
                if not next_entry:
                    continue

                visited.add(next_id_str)
                new_path = path + [{
                    "entry": next_entry,
                    "relationship": rel.relationship_type,
                    "direction": direction,
                }]
                chains.append(new_path)

                if len(new_path) <= max_depth:
                    queue.append((next_id, new_path))

        return chains

    async def find_typed_chain(
        self,
        start_entry_id: UUID,
        type_sequence: list[EntryType],
    ) -> list[list[BrainEntry]]:
        """Find chains matching a specific type sequence.

        Example: type_sequence=[IDEA, DECISION, TASK] finds paths like
        Idea → Decision → Task through relationships.

        Returns list of matching entry chains.
        """
        chains = await self.find_relationship_chain(
            start_entry_id, max_depth=len(type_sequence)
        )

        matching: list[list[BrainEntry]] = []
        for chain in chains:
            entries = [step["entry"] for step in chain]
            entry_types = [e.type for e in entries]

            # Check if the type sequence matches (partial match OK at start)
            if len(entry_types) >= len(type_sequence):
                if entry_types[: len(type_sequence)] == type_sequence:
                    matching.append(entries[: len(type_sequence)])
            elif entry_types == type_sequence[: len(entry_types)]:
                # Partial match — chain is shorter than requested sequence
                matching.append(entries)

        return matching

    # ── Depth-Limited Graph Walk ─────────────────────────────────

    async def walk_graph(
        self,
        start_entry_id: UUID,
        max_depth: int = 2,
        include_entity_links: bool = True,
    ) -> dict:
        """Depth-limited graph walk for related content discovery.

        Explores the knowledge graph from a starting entry, following
        both direct relationships and entity co-occurrence links.

        Returns:
            {
                "start": BrainEntry,
                "related_entries": [{
                    "entry": BrainEntry,
                    "distance": int,
                    "via": "relationship" | "entity",
                    "details": str,
                }, ...],
                "shared_entities": [Entity, ...],
            }
        """
        max_depth = min(max_depth, MAX_WALK_DEPTH)
        start_entry = await self.entry_repo.get_by_id(start_entry_id)
        if not start_entry:
            return {"start": None, "related_entries": [], "shared_entities": []}

        visited: set[str] = {str(start_entry_id)}
        related: list[dict] = []
        shared_entities: list[Entity] = []

        # BFS for relationship-linked entries
        queue: deque[tuple[UUID, int]] = deque()
        queue.append((start_entry_id, 0))

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            # Follow direct relationships
            rels = await self.entity_repo.get_relationships_for_entry(current_id)
            for rel in rels:
                next_id = (
                    rel.target_entry_id
                    if str(rel.source_entry_id) == str(current_id)
                    else rel.source_entry_id
                )
                next_id_str = str(next_id)
                if next_id_str in visited:
                    continue

                next_entry = await self.entry_repo.get_by_id(next_id)
                if not next_entry or next_entry.archived_at is not None:
                    continue

                visited.add(next_id_str)
                related.append({
                    "entry": next_entry,
                    "distance": depth + 1,
                    "via": "relationship",
                    "details": f"{rel.relationship_type.value} (confidence: {rel.confidence:.2f})",
                })
                queue.append((next_id, depth + 1))

        # Follow entity co-occurrence links (entries sharing entities)
        if include_entity_links:
            mentions = await self.entity_repo.get_mentions_for_entry(start_entry_id)
            seen_entity_ids: set[str] = set()

            for mention in mentions:
                entity_id_str = str(mention.entity_id)
                if entity_id_str in seen_entity_ids:
                    continue
                seen_entity_ids.add(entity_id_str)

                entity = await self.entity_repo.get_entity_by_id(mention.entity_id)
                if entity:
                    shared_entities.append(entity)

                linked_entry_ids = await self.entity_repo.get_entries_for_entity(
                    mention.entity_id
                )
                for linked_id_str in linked_entry_ids:
                    if linked_id_str in visited:
                        continue

                    linked_entry = await self.entry_repo.get_by_id(UUID(linked_id_str))
                    if not linked_entry or linked_entry.archived_at is not None:
                        continue

                    visited.add(linked_id_str)
                    entity_name = entity.name if entity else "unknown"
                    related.append({
                        "entry": linked_entry,
                        "distance": 1,
                        "via": "entity",
                        "details": f"shared entity: {entity_name}",
                    })

        # Sort by distance, then by created_at
        related.sort(key=lambda r: (r["distance"], -r["entry"].created_at.timestamp()))

        return {
            "start": start_entry,
            "related_entries": related,
            "shared_entities": shared_entities,
        }

    # ── Entity Co-occurrence ─────────────────────────────────────

    async def get_entity_cooccurrence(
        self, entity_id: UUID
    ) -> list[dict]:
        """Find entities that frequently co-occur with the given entity.

        Returns list of {"entity": Entity, "shared_entries": int} sorted
        by shared_entries descending.
        """
        # Get all entries mentioning this entity
        entry_ids = await self.entity_repo.get_entries_for_entity(entity_id)

        # For each entry, get its other entity mentions
        cooccurrence: dict[str, int] = defaultdict(int)  # entity_id -> count
        for entry_id_str in entry_ids:
            mentions = await self.entity_repo.get_mentions_for_entry(
                UUID(entry_id_str)
            )
            for mention in mentions:
                if str(mention.entity_id) != str(entity_id):
                    cooccurrence[str(mention.entity_id)] += 1

        # Resolve entity objects and sort
        results: list[dict] = []
        for ent_id_str, count in sorted(
            cooccurrence.items(), key=lambda x: x[1], reverse=True
        ):
            entity = await self.entity_repo.get_entity_by_id(UUID(ent_id_str))
            if entity:
                results.append({"entity": entity, "shared_entries": count})

        return results

    # ── Relationship Summary ─────────────────────────────────────

    async def get_entry_relationships_detail(
        self, entry_id: UUID
    ) -> dict:
        """Get detailed relationship info for an entry.

        Returns:
            {
                "entry": BrainEntry,
                "outgoing": [{"relationship": EntryRelationship, "target": BrainEntry}, ...],
                "incoming": [{"relationship": EntryRelationship, "source": BrainEntry}, ...],
            }
        """
        entry = await self.entry_repo.get_by_id(entry_id)
        if not entry:
            return {"entry": None, "outgoing": [], "incoming": []}

        rels = await self.entity_repo.get_relationships_for_entry(entry_id)

        outgoing: list[dict] = []
        incoming: list[dict] = []

        for rel in rels:
            if str(rel.source_entry_id) == str(entry_id):
                target = await self.entry_repo.get_by_id(rel.target_entry_id)
                if target:
                    outgoing.append({"relationship": rel, "target": target})
            else:
                source = await self.entry_repo.get_by_id(rel.source_entry_id)
                if source:
                    incoming.append({"relationship": rel, "source": source})

        return {"entry": entry, "outgoing": outgoing, "incoming": incoming}
