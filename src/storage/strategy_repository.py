"""Strategy repository — CRUD operations for strategic positioning entities."""

import json
from datetime import datetime, timezone
from uuid import UUID

import structlog

from src.models.enums import (
    AssetCategory,
    InitiativeCategory,
    InitiativeType,
    VisibilityLevel,
)
from src.models.strategy import (
    InfluenceDelta,
    Initiative,
    InitiativeLink,
    InitiativeScores,
    Stakeholder,
    StrategicAsset,
    WeeklySimulation,
)
from src.storage.database import Database

log = structlog.get_logger(__name__)


class StrategyRepository:
    """Repository for strategic positioning CRUD in SQLite."""

    def __init__(self, db: Database) -> None:
        self.db = db

    # ── Stakeholders ─────────────────────────────────────────────

    async def save_stakeholder(self, s: Stakeholder) -> Stakeholder:
        """Insert or replace a stakeholder."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO stakeholders (
                    id, name, role, influence_level, incentives,
                    alignment_score, dependency_on_you, trust_score,
                    notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(s.id), s.name, s.role, s.influence_level,
                    s.incentives, s.alignment_score, s.dependency_on_you,
                    s.trust_score, s.notes,
                    s.created_at.isoformat(), s.updated_at.isoformat(),
                ),
            )
            await conn.commit()
            log.info("stakeholder_saved", id=str(s.id), name=s.name)
        return s

    async def get_stakeholder(self, stakeholder_id: UUID) -> Stakeholder | None:
        """Retrieve a stakeholder by ID."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM stakeholders WHERE id = ?", (str(stakeholder_id),)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_stakeholder(row)

    async def list_stakeholders(self) -> list[Stakeholder]:
        """List all stakeholders ordered by influence level descending."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM stakeholders ORDER BY influence_level DESC, name ASC"
            )
            rows = await cursor.fetchall()
            return [self._row_to_stakeholder(r) for r in rows]

    async def delete_stakeholder(self, stakeholder_id: UUID) -> bool:
        """Delete a stakeholder by ID. Returns True if deleted."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM stakeholders WHERE id = ?", (str(stakeholder_id),)
            )
            await conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_stakeholder(row) -> Stakeholder:
        return Stakeholder(
            id=UUID(row["id"]),
            name=row["name"],
            role=row["role"],
            influence_level=row["influence_level"],
            incentives=row["incentives"],
            alignment_score=row["alignment_score"],
            dependency_on_you=row["dependency_on_you"],
            trust_score=row["trust_score"],
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    # ── Initiatives ──────────────────────────────────────────────

    async def save_initiative(self, init: Initiative) -> Initiative:
        """Insert or replace an initiative."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO initiatives (
                    id, title, description, initiative_type,
                    authority, asymmetric_info, future_mobility,
                    reusable_leverage, right_visibility,
                    category, visibility, risk_level, status,
                    linked_entry_ids, stakeholder_ids,
                    notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(init.id), init.title, init.description,
                    init.initiative_type.value,
                    init.scores.authority, init.scores.asymmetric_info,
                    init.scores.future_mobility, init.scores.reusable_leverage,
                    init.scores.right_visibility,
                    init.category.value, init.visibility.value,
                    init.risk_level, init.status,
                    json.dumps(init.linked_entry_ids),
                    json.dumps(init.stakeholder_ids),
                    init.notes, init.created_at.isoformat(),
                    init.updated_at.isoformat(),
                ),
            )
            await conn.commit()
            log.info("initiative_saved", id=str(init.id), title=init.title,
                     category=init.category.value, type=init.initiative_type.value)
        return init

    async def get_initiative(self, initiative_id: UUID) -> Initiative | None:
        """Retrieve an initiative by ID."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM initiatives WHERE id = ?", (str(initiative_id),)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_initiative(row)

    async def list_initiatives(
        self,
        status: str | None = None,
        category: InitiativeCategory | None = None,
        initiative_type: InitiativeType | None = None,
    ) -> list[Initiative]:
        """List initiatives with optional filtering."""
        query = "SELECT * FROM initiatives WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            params.append(category.value)
        if initiative_type:
            query += " AND initiative_type = ?"
            params.append(initiative_type.value)
        query += " ORDER BY created_at DESC"
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_initiative(r) for r in rows]

    async def find_initiatives_by_title(
        self, title: str, *, status: str | None = "active"
    ) -> list[Initiative]:
        """Find initiatives whose title fuzzy-matches the given string.

        Uses case-insensitive containment in both directions:
        initiative.title ⊇ query  OR  query ⊇ initiative.title.
        Returns matches ordered by best-fit-first (exact > contains > contained-by).
        """
        query = "SELECT * FROM initiatives WHERE 1=1"
        params: list = []
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC"

        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()

        needle = title.strip().lower()
        matches: list[tuple[int, Initiative]] = []
        for row in rows:
            init = self._row_to_initiative(row)
            hay = init.title.strip().lower()
            if hay == needle:
                matches.append((0, init))       # exact
            elif needle in hay:
                matches.append((1, init))       # query inside initiative title
            elif hay in needle:
                matches.append((2, init))       # initiative title inside query
        matches.sort(key=lambda t: t[0])
        return [m[1] for m in matches]

    async def link_exists(
        self, initiative_id: UUID, linked_id: str
    ) -> bool:
        """Check if a link already exists between an initiative and a target."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT 1 FROM initiative_links WHERE initiative_id = ? AND linked_id = ? LIMIT 1",
                (str(initiative_id), linked_id),
            )
            return (await cursor.fetchone()) is not None

    async def delete_initiative(self, initiative_id: UUID) -> bool:
        """Delete an initiative by ID."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM initiatives WHERE id = ?", (str(initiative_id),)
            )
            await conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_initiative(row) -> Initiative:
        scores = InitiativeScores(
            authority=row["authority"],
            asymmetric_info=row["asymmetric_info"],
            future_mobility=row["future_mobility"],
            reusable_leverage=row["reusable_leverage"],
            right_visibility=row["right_visibility"],
        )
        return Initiative(
            id=UUID(row["id"]),
            title=row["title"],
            description=row["description"],
            initiative_type=InitiativeType(row["initiative_type"]),
            scores=scores,
            category=InitiativeCategory(row["category"]),
            visibility=VisibilityLevel(row["visibility"]),
            risk_level=row["risk_level"],
            status=row["status"],
            linked_entry_ids=json.loads(row["linked_entry_ids"]),
            stakeholder_ids=json.loads(row["stakeholder_ids"]),
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    # ── Initiative Links ─────────────────────────────────────────

    async def save_initiative_link(self, link: InitiativeLink) -> InitiativeLink:
        """Insert a link from an initiative to an entry or entity."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO initiative_links (
                    id, initiative_id, linked_type, linked_id,
                    linked_title, link_note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(link.id), str(link.initiative_id),
                    link.linked_type, link.linked_id,
                    link.linked_title, link.link_note,
                    link.created_at.isoformat(),
                ),
            )
            await conn.commit()
            log.info("initiative_link_saved", initiative_id=str(link.initiative_id),
                     linked_type=link.linked_type, linked_id=link.linked_id)
        return link

    async def get_links_for_initiative(
        self, initiative_id: UUID
    ) -> list[InitiativeLink]:
        """Get all links for an initiative."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM initiative_links WHERE initiative_id = ? ORDER BY created_at DESC",
                (str(initiative_id),),
            )
            rows = await cursor.fetchall()
            return [self._row_to_link(r) for r in rows]

    async def get_initiatives_for_linked_item(
        self, linked_id: str
    ) -> list[InitiativeLink]:
        """Get all initiative links that reference a given entry or entity."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM initiative_links WHERE linked_id = ? ORDER BY created_at DESC",
                (linked_id,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_link(r) for r in rows]

    async def delete_initiative_link(self, link_id: UUID) -> bool:
        """Delete a specific initiative link."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM initiative_links WHERE id = ?", (str(link_id),)
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def count_links_for_initiative(self, initiative_id: UUID) -> int:
        """Count links for an initiative."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM initiative_links WHERE initiative_id = ?",
                (str(initiative_id),),
            )
            row = await cursor.fetchone()
            return row["cnt"] if row else 0

    @staticmethod
    def _row_to_link(row) -> InitiativeLink:
        return InitiativeLink(
            id=UUID(row["id"]),
            initiative_id=UUID(row["initiative_id"]),
            linked_type=row["linked_type"],
            linked_id=row["linked_id"],
            linked_title=row["linked_title"],
            link_note=row["link_note"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ── Strategic Assets ─────────────────────────────────────────

    async def save_asset(self, asset: StrategicAsset) -> StrategicAsset:
        """Insert or replace a strategic asset."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO strategic_assets (
                    id, title, description, asset_type, visibility,
                    reusability_score, signaling_strength, market_relevance,
                    compounding_potential, portability_score, market_demand,
                    monetization_potential, time_to_deploy,
                    linked_initiative_ids, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(asset.id), asset.title, asset.description,
                    asset.asset_type.value, asset.visibility.value,
                    asset.reusability_score, asset.signaling_strength,
                    asset.market_relevance, asset.compounding_potential,
                    asset.portability_score, asset.market_demand,
                    asset.monetization_potential, asset.time_to_deploy,
                    json.dumps(asset.linked_initiative_ids),
                    asset.notes, asset.created_at.isoformat(),
                    asset.updated_at.isoformat(),
                ),
            )
            await conn.commit()
            log.info("asset_saved", id=str(asset.id), title=asset.title,
                     type=asset.asset_type.value)
        return asset

    async def get_asset(self, asset_id: UUID) -> StrategicAsset | None:
        """Retrieve a strategic asset by ID."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM strategic_assets WHERE id = ?", (str(asset_id),)
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_asset(row)

    async def list_assets(
        self,
        asset_type: AssetCategory | None = None,
    ) -> list[StrategicAsset]:
        """List strategic assets with optional type filter."""
        if asset_type:
            query = "SELECT * FROM strategic_assets WHERE asset_type = ? ORDER BY created_at DESC"
            params: list = [asset_type.value]
        else:
            query = "SELECT * FROM strategic_assets ORDER BY created_at DESC"
            params = []
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_asset(r) for r in rows]

    async def delete_asset(self, asset_id: UUID) -> bool:
        """Delete a strategic asset by ID."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "DELETE FROM strategic_assets WHERE id = ?", (str(asset_id),)
            )
            await conn.commit()
            return cursor.rowcount > 0

    @staticmethod
    def _row_to_asset(row) -> StrategicAsset:
        return StrategicAsset(
            id=UUID(row["id"]),
            title=row["title"],
            description=row["description"],
            asset_type=AssetCategory(row["asset_type"]),
            visibility=VisibilityLevel(row["visibility"]),
            reusability_score=row["reusability_score"],
            signaling_strength=row["signaling_strength"],
            market_relevance=row["market_relevance"],
            compounding_potential=row["compounding_potential"],
            portability_score=row["portability_score"],
            market_demand=row["market_demand"],
            monetization_potential=row["monetization_potential"],
            time_to_deploy=row["time_to_deploy"],
            linked_initiative_ids=json.loads(row["linked_initiative_ids"]),
            notes=row["notes"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    # ── Influence Deltas ─────────────────────────────────────────

    async def save_influence_delta(self, delta: InfluenceDelta) -> InfluenceDelta:
        """Insert or replace an influence delta."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO influence_deltas (
                    id, week_start, stakeholder_id, stakeholder_name,
                    advice_sought, decision_changed,
                    framing_adopted, consultation_count, notes,
                    delta_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(delta.id), delta.week_start,
                    delta.stakeholder_id, delta.stakeholder_name,
                    1 if delta.advice_sought else 0,
                    1 if delta.decision_changed else 0,
                    1 if delta.framing_adopted else 0,
                    delta.consultation_count, delta.notes,
                    delta.delta_score,
                    delta.created_at.isoformat(),
                ),
            )
            await conn.commit()
            log.info("influence_delta_saved", id=str(delta.id),
                     week=delta.week_start, score=delta.delta_score,
                     stakeholder=delta.stakeholder_name)
        return delta

    async def list_influence_deltas(
        self, limit: int = 12
    ) -> list[InfluenceDelta]:
        """List recent influence deltas ordered by week descending."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM influence_deltas ORDER BY week_start DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_influence_delta(r) for r in rows]

    async def get_influence_delta_for_week(
        self, week_start: str
    ) -> InfluenceDelta | None:
        """Get the influence delta record for a specific week."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM influence_deltas WHERE week_start = ?",
                (week_start,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_influence_delta(row)

    @staticmethod
    def _row_to_influence_delta(row) -> InfluenceDelta:
        return InfluenceDelta(
            id=UUID(row["id"]),
            week_start=row["week_start"],
            stakeholder_id=row["stakeholder_id"] if "stakeholder_id" in row.keys() else None,
            stakeholder_name=row["stakeholder_name"] if "stakeholder_name" in row.keys() else None,
            advice_sought=bool(row["advice_sought"]),
            decision_changed=bool(row["decision_changed"]),
            framing_adopted=bool(row["framing_adopted"]),
            consultation_count=row["consultation_count"],
            notes=row["notes"],
            delta_score=row["delta_score"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ── Weekly Simulations ───────────────────────────────────────

    async def save_simulation(self, sim: WeeklySimulation) -> WeeklySimulation:
        """Insert or replace a weekly simulation."""
        async with self.db.get_connection() as conn:
            await conn.execute(
                """
                INSERT OR REPLACE INTO weekly_simulations (
                    id, week_start, strategic_move, maintenance_tasks,
                    position_building, influence_trend, optionality_trend,
                    top_initiatives, raw_analysis, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(sim.id), sim.week_start, sim.strategic_move,
                    json.dumps(sim.maintenance_tasks),
                    json.dumps(sim.position_building),
                    sim.influence_trend, sim.optionality_trend,
                    json.dumps(sim.top_initiatives),
                    sim.raw_analysis, sim.created_at.isoformat(),
                ),
            )
            await conn.commit()
            log.info("simulation_saved", id=str(sim.id), week=sim.week_start)
        return sim

    async def get_latest_simulation(self) -> WeeklySimulation | None:
        """Get the most recent weekly simulation."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM weekly_simulations ORDER BY week_start DESC LIMIT 1"
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return self._row_to_simulation(row)

    async def list_simulations(self, limit: int = 12) -> list[WeeklySimulation]:
        """List recent weekly simulations."""
        async with self.db.get_connection() as conn:
            cursor = await conn.execute(
                "SELECT * FROM weekly_simulations ORDER BY week_start DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [self._row_to_simulation(r) for r in rows]

    @staticmethod
    def _row_to_simulation(row) -> WeeklySimulation:
        return WeeklySimulation(
            id=UUID(row["id"]),
            week_start=row["week_start"],
            strategic_move=row["strategic_move"],
            maintenance_tasks=json.loads(row["maintenance_tasks"]),
            position_building=json.loads(row["position_building"]),
            influence_trend=row["influence_trend"],
            optionality_trend=row["optionality_trend"],
            top_initiatives=json.loads(row["top_initiatives"]),
            raw_analysis=row["raw_analysis"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    # ── Aggregate Queries ────────────────────────────────────────

    async def get_strategy_summary(self) -> dict:
        """Aggregate summary for the strategy dashboard."""
        async with self.db.get_connection() as conn:
            # Initiative counts by category
            cursor = await conn.execute(
                "SELECT category, COUNT(*) as cnt FROM initiatives "
                "WHERE status = 'active' GROUP BY category"
            )
            initiative_counts = {
                row["category"]: row["cnt"] for row in await cursor.fetchall()
            }

            # Asset counts by type
            cursor = await conn.execute(
                "SELECT asset_type, COUNT(*) as cnt FROM strategic_assets "
                "GROUP BY asset_type"
            )
            asset_counts = {
                row["asset_type"]: row["cnt"] for row in await cursor.fetchall()
            }

            # Stakeholder count
            cursor = await conn.execute("SELECT COUNT(*) as cnt FROM stakeholders")
            row = await cursor.fetchone()
            stakeholder_count = row["cnt"] if row else 0

            # Influence trend (last 4 weeks)
            cursor = await conn.execute(
                "SELECT delta_score FROM influence_deltas "
                "ORDER BY week_start DESC LIMIT 4"
            )
            recent_deltas = [r["delta_score"] for r in await cursor.fetchall()]

            # Visibility distribution of active initiatives
            cursor = await conn.execute(
                "SELECT visibility, COUNT(*) as cnt FROM initiatives "
                "WHERE status = 'active' GROUP BY visibility"
            )
            visibility_dist = {
                row["visibility"]: row["cnt"] for row in await cursor.fetchall()
            }

        return {
            "initiative_counts": initiative_counts,
            "asset_counts": asset_counts,
            "stakeholder_count": stakeholder_count,
            "recent_influence_deltas": recent_deltas,
            "visibility_distribution": visibility_dist,
        }
