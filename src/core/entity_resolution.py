"""Entity resolution — match extracted entities against known entities."""

import json
from datetime import datetime, timezone
from uuid import UUID

import structlog

from src.models.brain_entry import Entity, EntityMention, EntryRelationship
from src.models.enums import EntityType, NoveltyVerdict, RelationshipType
from src.storage.database import Database

log = structlog.get_logger(__name__)

# Minimum similarity ratio for fuzzy name matching (0-1)
FUZZY_MATCH_THRESHOLD = 0.75

# Default semantic similarity thresholds per entity type
DEFAULT_SEMANTIC_THRESHOLDS: dict[EntityType, float] = {
    EntityType.PERSON: 0.80,
    EntityType.TECHNOLOGY: 0.75,
    EntityType.PROJECT: 0.75,
    EntityType.CONCEPT: 0.65,
    EntityType.ORGANIZATION: 0.75,
}


class EntityRepository:
    """CRUD operations for entities, mentions, and relationships."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ── Entity CRUD ──────────────────────────────────────────────

    async def save_entity(self, entity: Entity) -> Entity:
        """Insert or update an entity."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO entities (
                    id, name, entity_type, aliases, description,
                    created_at, updated_at, entry_count, embedding_vector_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    aliases = excluded.aliases,
                    description = excluded.description,
                    updated_at = excluded.updated_at,
                    entry_count = excluded.entry_count,
                    embedding_vector_id = excluded.embedding_vector_id
                """,
                (
                    str(entity.id),
                    entity.name,
                    entity.entity_type.value,
                    json.dumps(entity.aliases),
                    entity.description,
                    entity.created_at.isoformat(),
                    entity.updated_at.isoformat(),
                    entity.entry_count,
                    entity.embedding_vector_id,
                ),
            )
            await conn.commit()
        return entity

    async def get_entity_by_id(self, entity_id: UUID) -> Entity | None:
        """Retrieve an entity by ID."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM entities WHERE id = ?", (str(entity_id),)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_entity(row)

    async def get_all_entities(self) -> list[Entity]:
        """Retrieve all entities, ordered by entry_count descending."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM entities ORDER BY entry_count DESC"
            )
            rows = await cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]

    async def search_entities_by_name(self, name: str) -> list[Entity]:
        """Find entities whose name or aliases match (case-insensitive LIKE)."""
        pattern = f"%{name}%"
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM entities
                WHERE name LIKE ? COLLATE NOCASE
                   OR aliases LIKE ? COLLATE NOCASE
                ORDER BY entry_count DESC
                """,
                (pattern, pattern),
            )
            rows = await cursor.fetchall()
            return [self._row_to_entity(row) for row in rows]

    async def update_entity(
        self,
        entity_id: UUID,
        *,
        name: str | None = None,
        entity_type: EntityType | None = None,
        description: str | None = None,
        aliases: list[str] | None = None,
    ) -> Entity | None:
        """Update an entity's editable fields. Returns updated entity or None."""
        entity = await self.get_entity_by_id(entity_id)
        if not entity:
            return None

        if name is not None:
            entity.name = name
        if entity_type is not None:
            entity.entity_type = entity_type
        if description is not None:
            entity.description = description
        if aliases is not None:
            entity.aliases = aliases
        entity.updated_at = datetime.now(timezone.utc)

        await self.save_entity(entity)
        return entity

    async def delete_entity(self, entity_id: UUID) -> bool:
        """Delete an entity and all its mentions. Returns True if deleted."""
        async with self.db.get_connection() as conn:
            # Delete mentions first
            await conn.execute(
                "DELETE FROM entity_mentions WHERE entity_id = ?",
                (str(entity_id),),
            )
            # Delete entity summary if exists
            await conn.execute(
                "DELETE FROM entity_summaries WHERE entity_id = ?",
                (str(entity_id),),
            )
            # Delete the entity
            cursor = await conn.execute(
                "DELETE FROM entities WHERE id = ?",
                (str(entity_id),),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def increment_entry_count(self, entity_id: UUID) -> None:
        """Bump entry_count by 1 and update updated_at."""
        now = datetime.now(timezone.utc).isoformat()
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                UPDATE entities
                SET entry_count = entry_count + 1, updated_at = ?
                WHERE id = ?
                """,
                (now, str(entity_id)),
            )
            await conn.commit()

    # ── Entity Mention CRUD ──────────────────────────────────────

    async def save_mention(self, mention: EntityMention) -> EntityMention:
        """Record that an entity was mentioned in an entry."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO entity_mentions (
                    id, entity_id, entry_id, mention_text, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(mention.id),
                    str(mention.entity_id),
                    str(mention.entry_id),
                    mention.mention_text,
                    mention.created_at.isoformat(),
                ),
            )
            await conn.commit()
        return mention

    async def get_mentions_for_entry(self, entry_id: UUID) -> list[EntityMention]:
        """Get all entity mentions in a given entry."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM entity_mentions WHERE entry_id = ?",
                (str(entry_id),),
            )
            rows = await cursor.fetchall()
            return [self._row_to_mention(row) for row in rows]

    async def get_entries_for_entity(self, entity_id: UUID) -> list[str]:
        """Get all entry IDs linked to an entity."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT DISTINCT entry_id FROM entity_mentions WHERE entity_id = ?",
                (str(entity_id),),
            )
            rows = await cursor.fetchall()
            return [row["entry_id"] for row in rows]

    # ── Relationship CRUD ────────────────────────────────────────

    async def save_relationship(self, rel: EntryRelationship) -> EntryRelationship:
        """Save a directional relationship between two entries."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO entry_relationships (
                    id, source_entry_id, target_entry_id,
                    relationship_type, confidence, created_at, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(rel.id),
                    str(rel.source_entry_id),
                    str(rel.target_entry_id),
                    rel.relationship_type.value,
                    rel.confidence,
                    rel.created_at.isoformat(),
                    rel.reason,
                ),
            )
            await conn.commit()
        return rel

    async def get_relationships_for_entry(
        self, entry_id: UUID
    ) -> list[EntryRelationship]:
        """Get all relationships where this entry is source OR target."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT * FROM entry_relationships
                WHERE source_entry_id = ? OR target_entry_id = ?
                ORDER BY created_at DESC
                """,
                (str(entry_id), str(entry_id)),
            )
            rows = await cursor.fetchall()
            return [self._row_to_relationship(row) for row in rows]

    # ── Row converters ───────────────────────────────────────────

    @staticmethod
    def _row_to_entity(row) -> Entity:
        return Entity(
            id=UUID(row["id"]),
            name=row["name"],
            entity_type=EntityType(row["entity_type"]),
            aliases=json.loads(row["aliases"]),
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            entry_count=row["entry_count"],
            embedding_vector_id=row["embedding_vector_id"],
        )

    @staticmethod
    def _row_to_mention(row) -> EntityMention:
        return EntityMention(
            id=UUID(row["id"]),
            entity_id=UUID(row["entity_id"]),
            entry_id=UUID(row["entry_id"]),
            mention_text=row["mention_text"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    async def delete_relationship(self, relationship_id: UUID) -> bool:
        """Delete an entry relationship by ID."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM entry_relationships WHERE id = ?",
                (str(relationship_id),),
            )
            await conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_relationship(row) -> EntryRelationship:
        return EntryRelationship(
            id=UUID(row["id"]),
            source_entry_id=UUID(row["source_entry_id"]),
            target_entry_id=UUID(row["target_entry_id"]),
            relationship_type=RelationshipType(row["relationship_type"]),
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]),
            reason=row["reason"],
        )


class EntityResolver:
    """Resolves extracted entity names against known entities.

    For each entity name the LLM extracts from a message, this service:
    1. Searches existing entities by name/alias (exact + fuzzy)
    2. Falls back to semantic (embedding) similarity if no fuzzy match
    3. If a match is found → links to existing entity
    4. If no match → creates a new entity and embeds it

    Also determines novelty: is the incoming entry new information,
    or does it augment an existing entry about the same entities?
    """

    def __init__(
        self,
        entity_repo: EntityRepository,
        vector_store: "VectorStore | None" = None,
        provider: "LLMProvider | None" = None,
        semantic_thresholds: dict[EntityType, float] | None = None,
    ) -> None:
        self.entity_repo = entity_repo
        self.vector_store = vector_store
        self.provider = provider
        self.semantic_thresholds = semantic_thresholds or DEFAULT_SEMANTIC_THRESHOLDS

    async def resolve_entities(
        self,
        extracted: list[dict],
        entry_id: UUID,
    ) -> list[Entity]:
        """Match extracted entity dicts against known entities.

        Args:
            extracted: list of {"name": str, "type": str} from the classifier
            entry_id: the brain entry these entities belong to

        Returns:
            list of resolved Entity objects (existing or newly created)
        """
        resolved: list[Entity] = []

        for ent_dict in extracted:
            name = ent_dict.get("name", "").strip()
            if not name:
                continue

            ent_type_str = ent_dict.get("type", "concept")
            try:
                ent_type = EntityType(ent_type_str)
            except ValueError:
                ent_type = EntityType.CONCEPT

            # Search for existing match
            match = await self._find_match(name, ent_type)

            if match:
                entity = match
                # Add this name as alias if it's different
                if name.lower() != entity.name.lower() and name.lower() not in [
                    a.lower() for a in entity.aliases
                ]:
                    entity.aliases.append(name)
                    await self.entity_repo.save_entity(entity)

                await self.entity_repo.increment_entry_count(entity.id)
                log.info(
                    "entity_matched",
                    entity_name=entity.name,
                    mention=name,
                    entry_id=str(entry_id),
                )
            else:
                # Create new entity
                entity = Entity(
                    name=name,
                    entity_type=ent_type,
                )
                entity.entry_count = 1
                await self.entity_repo.save_entity(entity)

                # Embed the entity for future semantic matching
                await self._embed_entity(entity)

                log.info(
                    "entity_created",
                    entity_name=entity.name,
                    entity_type=ent_type.value,
                    entry_id=str(entry_id),
                )

            # Record the mention
            mention = EntityMention(
                entity_id=entity.id,
                entry_id=entry_id,
                mention_text=name,
            )
            await self.entity_repo.save_mention(mention)

            resolved.append(entity)

        return resolved

    async def assess_novelty(
        self,
        resolved_entities: list[Entity],
        entry_id: UUID,
    ) -> tuple[NoveltyVerdict, UUID | None]:
        """Determine if this entry is new knowledge or augments an existing entry.

        Heuristic:
        - If any resolved entity has entry_count > 1, check if there are
          existing entries sharing multiple entities.
        - If overlap >= 2 entities with the same entry, mark as AUGMENT.
        - Otherwise, mark as NEW.

        Returns:
            (NoveltyVerdict, augments_entry_id or None)
        """
        if not resolved_entities:
            return NoveltyVerdict.NEW, None

        # Collect all entry IDs linked to the resolved entities (excluding current)
        entry_entity_overlap: dict[str, int] = {}  # entry_id -> count of shared entities

        for entity in resolved_entities:
            if entity.entry_count <= 1:
                continue
            linked_entry_ids = await self.entity_repo.get_entries_for_entity(entity.id)
            for linked_id in linked_entry_ids:
                if linked_id == str(entry_id):
                    continue
                entry_entity_overlap[linked_id] = (
                    entry_entity_overlap.get(linked_id, 0) + 1
                )

        if not entry_entity_overlap:
            return NoveltyVerdict.NEW, None

        # Find the entry with highest entity overlap
        best_id, best_count = max(
            entry_entity_overlap.items(), key=lambda x: x[1]
        )

        if best_count >= 2:
            log.info(
                "novelty_augment",
                entry_id=str(entry_id),
                augments=best_id,
                shared_entities=best_count,
            )
            return NoveltyVerdict.AUGMENT, UUID(best_id)

        return NoveltyVerdict.NEW, None

    async def _find_match(self, name: str, entity_type: EntityType = EntityType.CONCEPT) -> Entity | None:
        """Find an existing entity that matches this name.

        Matching strategy (in order):
        1. Exact name/alias match (case-insensitive)
        2. Fuzzy bigram matching (Dice coefficient >= threshold)
        3. Semantic embedding similarity (if vector store + provider available)
        """
        candidates = await self.entity_repo.search_entities_by_name(name)

        if candidates:
            # Exact match first (case-insensitive)
            for c in candidates:
                if c.name.lower() == name.lower():
                    return c
                if name.lower() in [a.lower() for a in c.aliases]:
                    return c

            # Fuzzy match using simple ratio
            for c in candidates:
                if self._similarity(c.name.lower(), name.lower()) >= FUZZY_MATCH_THRESHOLD:
                    return c
                for alias in c.aliases:
                    if self._similarity(alias.lower(), name.lower()) >= FUZZY_MATCH_THRESHOLD:
                        return c

        # Semantic matching fallback (Phase 2)
        semantic_match = await self._find_semantic_match(name, entity_type)
        if semantic_match:
            return semantic_match

        return None

    async def _find_semantic_match(
        self, name: str, entity_type: EntityType = EntityType.CONCEPT
    ) -> Entity | None:
        """Find an entity by embedding similarity in vector space.

        Returns the best-matching entity if its similarity score exceeds the
        per-type threshold, or None if no match is found.
        """
        if not self.vector_store or not self.provider:
            return None

        try:
            # Embed the candidate name
            query_vector = await self.provider.embed(name)
            if not query_vector:
                return None

            # Search entity vectors
            results = await self.vector_store.search_entities(query_vector, limit=5)
            if not results:
                return None

            threshold = self.semantic_thresholds.get(
                entity_type,
                DEFAULT_SEMANTIC_THRESHOLDS.get(entity_type, 0.70),
            )

            for entity_id_str, score in results:
                if score >= threshold:
                    entity = await self.entity_repo.get_entity_by_id(
                        UUID(entity_id_str)
                    )
                    if entity:
                        log.info(
                            "semantic_entity_match",
                            query=name,
                            matched_entity=entity.name,
                            score=score,
                            threshold=threshold,
                        )
                        return entity

        except Exception as e:
            log.warning("semantic_entity_match_failed", name=name, error=str(e))

        return None

    async def _embed_entity(self, entity: Entity) -> None:
        """Generate and store an embedding vector for an entity.

        Uses the entity name + aliases + description as embedding text.
        Gracefully degrades if vector store or provider is unavailable.
        """
        if not self.vector_store or not self.provider:
            return

        try:
            # Build representative text for embedding
            parts = [entity.name]
            if entity.aliases:
                parts.extend(entity.aliases)
            if entity.description:
                parts.append(entity.description)
            embed_text = " | ".join(parts)

            vector = await self.provider.embed(embed_text)
            if not vector:
                return

            await self.vector_store.upsert_entity(
                id=str(entity.id),
                vector=vector,
                payload={
                    "name": entity.name,
                    "entity_type": entity.entity_type.value,
                },
            )
            entity.embedding_vector_id = str(entity.id)
            await self.entity_repo.save_entity(entity)
            log.debug("entity_embedded", entity_name=entity.name)
        except Exception as e:
            log.warning(
                "entity_embedding_failed",
                entity_name=entity.name,
                error=str(e),
            )

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """Simple character-level similarity ratio (Dice coefficient on bigrams).

        Returns 0.0-1.0 where 1.0 is identical.
        """
        if a == b:
            return 1.0
        if len(a) < 2 or len(b) < 2:
            return 0.0

        bigrams_a = {a[i : i + 2] for i in range(len(a) - 1)}
        bigrams_b = {b[i : i + 2] for i in range(len(b) - 1)}

        intersection = len(bigrams_a & bigrams_b)
        return (2.0 * intersection) / (len(bigrams_a) + len(bigrams_b))
