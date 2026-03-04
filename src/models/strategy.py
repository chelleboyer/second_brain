"""Strategic positioning domain models — Phase II."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.models.enums import (
    AssetCategory,
    InitiativeCategory,
    InitiativeType,
    VisibilityLevel,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Stakeholder ──────────────────────────────────────────────────


class Stakeholder(BaseModel):
    """A person whose influence dynamics are tracked.

    Models how much a stakeholder depends on you, trusts you,
    and how aligned their incentives are with yours.
    """

    id: UUID = Field(default_factory=uuid4)
    name: str
    role: str = ""
    influence_level: int = Field(default=5, ge=0, le=10)
    incentives: str = ""
    alignment_score: int = Field(default=0, ge=-5, le=5)
    dependency_on_you: int = Field(default=0, ge=0, le=10)
    trust_score: int = Field(default=5, ge=0, le=10)
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class StakeholderCreate(BaseModel):
    """Input model for creating a stakeholder."""

    name: str
    role: str = ""
    influence_level: int = Field(default=5, ge=0, le=10)
    incentives: str = ""
    alignment_score: int = Field(default=0, ge=-5, le=5)
    dependency_on_you: int = Field(default=0, ge=0, le=10)
    trust_score: int = Field(default=5, ge=0, le=10)
    notes: str = ""


# ── Initiative ───────────────────────────────────────────────────


class InitiativeScores(BaseModel):
    """Five-criteria scoring for the Move Evaluation Engine.

    Each criterion scored 0–5. Total determines category:
    - <12 → Maintenance
    - 12–17 → Supportive
    - 18+ → Strategic
    """

    authority: int = Field(default=0, ge=0, le=5)
    asymmetric_info: int = Field(default=0, ge=0, le=5)
    future_mobility: int = Field(default=0, ge=0, le=5)
    reusable_leverage: int = Field(default=0, ge=0, le=5)
    right_visibility: int = Field(default=0, ge=0, le=5)

    @property
    def total(self) -> int:
        return (
            self.authority
            + self.asymmetric_info
            + self.future_mobility
            + self.reusable_leverage
            + self.right_visibility
        )

    @property
    def category(self) -> InitiativeCategory:
        total = self.total
        if total >= 18:
            return InitiativeCategory.STRATEGIC
        elif total >= 12:
            return InitiativeCategory.SUPPORTIVE
        else:
            return InitiativeCategory.MAINTENANCE


class Initiative(BaseModel):
    """A project or effort evaluated for strategic positioning impact.

    Links to brain entries for traceability, carries a five-dimension
    strategic score, and tracks risk and visibility.
    """

    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str = ""
    initiative_type: InitiativeType = InitiativeType.SCORED
    scores: InitiativeScores = Field(default_factory=InitiativeScores)
    category: InitiativeCategory = InitiativeCategory.MAINTENANCE
    visibility: VisibilityLevel = VisibilityLevel.HIDDEN
    risk_level: int = Field(default=0, ge=0, le=5)
    status: str = "active"  # active, completed, paused, abandoned
    linked_entry_ids: list[str] = Field(default_factory=list)
    stakeholder_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class InitiativeCreate(BaseModel):
    """Input model for creating an initiative."""

    title: str
    description: str = ""
    initiative_type: InitiativeType = InitiativeType.SCORED
    authority: int = Field(default=0, ge=0, le=5)
    asymmetric_info: int = Field(default=0, ge=0, le=5)
    future_mobility: int = Field(default=0, ge=0, le=5)
    reusable_leverage: int = Field(default=0, ge=0, le=5)
    right_visibility: int = Field(default=0, ge=0, le=5)
    visibility: VisibilityLevel = VisibilityLevel.HIDDEN
    risk_level: int = Field(default=0, ge=0, le=5)
    notes: str = ""


# ── Initiative Link ───────────────────────────────────────────────


class InitiativeLink(BaseModel):
    """A link from an initiative to a brain entry or entity.

    Connects mandatory or scored initiatives to the knowledge
    graph, making relationships between work and captured
    knowledge explicit and navigable.
    """

    id: UUID = Field(default_factory=uuid4)
    initiative_id: UUID
    linked_type: str  # 'entry' or 'entity'
    linked_id: str  # UUID as string
    linked_title: str = ""  # Denormalized for display
    link_note: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class InitiativeLinkCreate(BaseModel):
    """Input model for creating an initiative link."""

    linked_type: str  # 'entry' or 'entity'
    linked_id: str
    link_note: str = ""


# ── Strategic Asset ──────────────────────────────────────────────


class StrategicAsset(BaseModel):
    """A reputation or optionality asset — a compounding strategic output.

    Reputation assets increase perceived authority and credibility.
    Optionality assets increase market mobility and independence.
    """

    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str = ""
    asset_type: AssetCategory = AssetCategory.REPUTATION
    visibility: VisibilityLevel = VisibilityLevel.HIDDEN

    # Reputation attributes
    reusability_score: int = Field(default=0, ge=0, le=10)
    signaling_strength: int = Field(default=0, ge=0, le=10)
    market_relevance: int = Field(default=0, ge=0, le=10)
    compounding_potential: int = Field(default=0, ge=0, le=10)

    # Optionality attributes
    portability_score: int = Field(default=0, ge=0, le=10)
    market_demand: int = Field(default=0, ge=0, le=10)
    monetization_potential: int = Field(default=0, ge=0, le=10)
    time_to_deploy: int = Field(default=0, ge=0, le=10)  # Lower = faster

    linked_initiative_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @property
    def reputation_score(self) -> float:
        """Composite reputation score (0-10). Average of reputation attributes."""
        return (
            self.reusability_score
            + self.signaling_strength
            + self.market_relevance
            + self.compounding_potential
        ) / 4.0

    @property
    def optionality_score(self) -> float:
        """Composite optionality score (0-10). Average of optionality attributes."""
        return (
            self.portability_score
            + self.market_demand
            + self.monetization_potential
            + (10 - self.time_to_deploy)  # Invert: lower deploy time = higher score
        ) / 4.0


class StrategicAssetCreate(BaseModel):
    """Input model for creating a strategic asset."""

    title: str
    description: str = ""
    asset_type: AssetCategory = AssetCategory.REPUTATION
    visibility: VisibilityLevel = VisibilityLevel.HIDDEN
    reusability_score: int = Field(default=0, ge=0, le=10)
    signaling_strength: int = Field(default=0, ge=0, le=10)
    market_relevance: int = Field(default=0, ge=0, le=10)
    compounding_potential: int = Field(default=0, ge=0, le=10)
    portability_score: int = Field(default=0, ge=0, le=10)
    market_demand: int = Field(default=0, ge=0, le=10)
    monetization_potential: int = Field(default=0, ge=0, le=10)
    time_to_deploy: int = Field(default=0, ge=0, le=10)
    notes: str = ""


# ── Influence Delta ──────────────────────────────────────────────


class InfluenceDelta(BaseModel):
    """Weekly influence tracking record.

    Logs key interactions and calculates whether influence
    is growing (+) or declining (-) over time.
    """

    id: UUID = Field(default_factory=uuid4)
    week_start: str  # ISO date string e.g. "2026-03-02"
    stakeholder_id: str | None = None  # UUID string of related stakeholder
    stakeholder_name: str | None = None  # Denormalized for display
    advice_sought: bool = False
    advice_detail: str = ""  # What specific advice was sought
    decision_changed: bool = False
    decision_detail: str = ""  # What decision changed and how
    framing_adopted: bool = False
    framing_detail: str = ""  # What framing was adopted and where
    consultation_count: int = Field(default=0, ge=0)
    notes: str = ""
    delta_score: int = Field(default=0, ge=-10, le=10)
    created_at: datetime = Field(default_factory=_utcnow)

    @property
    def computed_delta(self) -> int:
        """Auto-compute influence delta from interaction data."""
        score = 0
        if self.advice_sought:
            score += 2
        if self.decision_changed:
            score += 3
        if self.framing_adopted:
            score += 3
        score += min(self.consultation_count, 4)  # Cap contribution
        return min(score, 10)


class InfluenceDeltaCreate(BaseModel):
    """Input model for logging a weekly influence delta."""

    week_start: str
    stakeholder_id: str | None = None  # UUID string of related stakeholder
    advice_sought: bool = False
    advice_detail: str = ""  # What specific advice was sought
    decision_changed: bool = False
    decision_detail: str = ""  # What decision changed and how
    framing_adopted: bool = False
    framing_detail: str = ""  # What framing was adopted and where
    consultation_count: int = Field(default=0, ge=0)
    notes: str = ""


# ── Weekly Simulation ────────────────────────────────────────────


class Friction(BaseModel):
    """An organizational or operational friction point.

    Tracks recurring pain points, their severity, and relationships
    to stakeholders and initiatives. Frictions surface what is
    slowing things down and connect to countermeasures.
    """

    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str = ""
    category: str = ""  # e.g. Operations, Data Quality, Delivery, Infrastructure
    severity: int = Field(default=3, ge=1, le=5)
    frequency: int = Field(default=3, ge=1, le=5)
    blast_radius: int = Field(default=3, ge=1, le=5)
    owner_role: str = ""
    affected_stakeholders: list[str] = Field(default_factory=list)
    related_initiatives: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    countermeasures: list[str] = Field(default_factory=list)
    notes: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @property
    def impact_score(self) -> float:
        """Composite impact score (1-5). Weighted average of severity, frequency, and blast radius."""
        return round((self.severity * 0.4 + self.frequency * 0.3 + self.blast_radius * 0.3), 1)


class FrictionCreate(BaseModel):
    """Input model for creating a friction."""

    title: str
    description: str = ""
    category: str = ""
    severity: int = Field(default=3, ge=1, le=5)
    frequency: int = Field(default=3, ge=1, le=5)
    blast_radius: int = Field(default=3, ge=1, le=5)
    owner_role: str = ""
    affected_stakeholders: str = ""  # Comma-separated for form input
    related_initiatives: str = ""  # Comma-separated for form input
    signals: str = ""  # Newline-separated for form input
    countermeasures: str = ""  # Newline-separated for form input
    notes: str = ""


class WeeklySimulation(BaseModel):
    """Output of the weekly strategic simulation protocol.

    Produced every week — identifies the dominant next move,
    maintenance tasks, and position-building priorities.
    """

    id: UUID = Field(default_factory=uuid4)
    week_start: str  # ISO date string
    strategic_move: str = ""
    maintenance_tasks: list[str] = Field(default_factory=list)
    position_building: list[str] = Field(default_factory=list)
    influence_trend: str = ""  # up, down, flat
    optionality_trend: str = ""  # up, down, flat
    top_initiatives: list[str] = Field(default_factory=list)
    raw_analysis: str = ""  # Full LLM analysis text
    created_at: datetime = Field(default_factory=_utcnow)
