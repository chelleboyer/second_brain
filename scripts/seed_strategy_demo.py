"""Seed the Reputation & Optionality Engine with realistic demo data.

Run:
    python -m scripts.seed_strategy_demo

Populates stakeholders, initiatives, strategic assets, and influence
deltas so the Strategy dashboard has meaningful content to explore.
"""

import asyncio
import sys
from pathlib import Path

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.enums import (
    AssetCategory,
    InitiativeCategory,
    InitiativeType,
    VisibilityLevel,
)
from src.models.strategy import (
    InfluenceDelta,
    Initiative,
    InitiativeScores,
    Stakeholder,
    StrategicAsset,
)
from src.config import get_settings
from src.storage.database import Database
from src.storage.strategy_repository import StrategyRepository


# ── Stakeholders ────────────────────────────────────────────────

STAKEHOLDERS = [
    Stakeholder(
        name="David Chen",
        role="VP of Engineering",
        influence_level=9,
        incentives="Ship reliable platform; reduce incident count; justify headcount",
        alignment_score=3,
        dependency_on_you=6,
        trust_score=8,
        notes="Relies on your architectural recommendations. Championed the AI initiative.",
    ),
    Stakeholder(
        name="Priya Kapoor",
        role="Director of Product",
        influence_level=8,
        incentives="Revenue growth features; faster time-to-market; OKR visibility",
        alignment_score=2,
        dependency_on_you=4,
        trust_score=7,
        notes="Values data-driven arguments. Key ally for strategic visibility.",
    ),
    Stakeholder(
        name="Marcus Wright",
        role="CTO",
        influence_level=10,
        incentives="Technical vision; board-level narrative; competitive moat",
        alignment_score=4,
        dependency_on_you=3,
        trust_score=6,
        notes="Limited direct interaction. Sees you through David's reports.",
    ),
    Stakeholder(
        name="Jasmine Torres",
        role="Staff Engineer — Platform",
        influence_level=6,
        incentives="Technical excellence; peer recognition; open-source profile",
        alignment_score=1,
        dependency_on_you=5,
        trust_score=9,
        notes="Close collaborator. Co-owns the RAG platform work. High mutual trust.",
    ),
    Stakeholder(
        name="Ryan Liu",
        role="Engineering Manager — ML Team",
        influence_level=7,
        incentives="Team growth; model quality metrics; cross-functional wins",
        alignment_score=0,
        dependency_on_you=2,
        trust_score=5,
        notes="Neutral stakeholder. Could become ally if you contribute to embedding pipeline.",
    ),
]


# ── Initiatives ─────────────────────────────────────────────────

INITIATIVES = [
    # Strategic (18+)
    Initiative(
        title="AI-Native Architecture Blueprint",
        description="Design and publish the company-wide reference architecture for AI-native services. Defines embedding pipelines, retrieval patterns, and guardrails.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=5,
            asymmetric_info=4,
            future_mobility=4,
            reusable_leverage=5,
            right_visibility=4,
        ),
        category=InitiativeCategory.STRATEGIC,
        visibility=VisibilityLevel.EXECUTIVE,
        risk_level=2,
        notes="Positions you as the AI architecture authority. Publish internally first, then externally.",
    ),
    Initiative(
        title="Second Brain Open-Source Release",
        description="Package the cognitive capture engine as an open-source project. Demonstrates systems thinking and creates external credibility.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=4,
            asymmetric_info=3,
            future_mobility=5,
            reusable_leverage=5,
            right_visibility=5,
        ),
        category=InitiativeCategory.STRATEGIC,
        visibility=VisibilityLevel.MARKET,
        risk_level=3,
        notes="High optionality value. Requires IP review before publishing.",
    ),
    # Supportive (12–17)
    Initiative(
        title="RAG Retrieval Quality Improvements",
        description="Improve recall@10 by 15% through hybrid search, re-ranking, and chunk optimization.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=3,
            asymmetric_info=3,
            future_mobility=3,
            reusable_leverage=3,
            right_visibility=2,
        ),
        category=InitiativeCategory.SUPPORTIVE,
        visibility=VisibilityLevel.LOCAL,
        risk_level=1,
        notes="Solid skill builder. Results are measurable and demonstrable.",
    ),
    Initiative(
        title="Engineering Onboarding Playbook",
        description="Create a structured onboarding playbook for new engineers, covering architecture, conventions, and tooling.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=3,
            asymmetric_info=1,
            future_mobility=2,
            reusable_leverage=4,
            right_visibility=3,
        ),
        category=InitiativeCategory.SUPPORTIVE,
        visibility=VisibilityLevel.LOCAL,
        risk_level=1,
        notes="Creates leverage — others onboard faster. Makes you the 'systems thinker' on the team.",
    ),
    # Maintenance (<12)
    Initiative(
        title="CI Pipeline Maintenance",
        description="Keep CI green: fix flaky tests, update dependencies, manage build caching.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=1,
            asymmetric_info=0,
            future_mobility=1,
            reusable_leverage=1,
            right_visibility=1,
        ),
        category=InitiativeCategory.MAINTENANCE,
        visibility=VisibilityLevel.HIDDEN,
        risk_level=1,
        notes="Necessary but invisible. Minimize time here.",
    ),
    Initiative(
        title="Quarterly Security Patches",
        description="Apply dependency security patches, rotate credentials, review access controls.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=1,
            asymmetric_info=1,
            future_mobility=0,
            reusable_leverage=0,
            right_visibility=0,
        ),
        category=InitiativeCategory.MAINTENANCE,
        visibility=VisibilityLevel.HIDDEN,
        risk_level=2,
        notes="Compliance requirement. Block time, don't gold-plate.",
    ),
    # Mandatory (no scoring — value is relational)
    Initiative(
        title="Platform Incident Response",
        description="On-call rotation and incident response for the AI platform services.",
        initiative_type=InitiativeType.MANDATORY,
        scores=InitiativeScores(),
        category=InitiativeCategory.MAINTENANCE,
        visibility=VisibilityLevel.LOCAL,
        risk_level=3,
        notes="Mandatory but use incidents to demonstrate calm, clear leadership under pressure.",
    ),
]


# ── Strategic Assets ────────────────────────────────────────────

ASSETS = [
    # Reputation assets
    StrategicAsset(
        title="AI Architecture Decision Records",
        description="Collection of 12 ADRs documenting AI system design decisions, trade-offs, and rationale. Referenced by 3 teams.",
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.EXECUTIVE,
        reusability_score=8,
        signaling_strength=7,
        market_relevance=6,
        compounding_potential=9,
        notes="High compounding — each new ADR increases the set's authority.",
    ),
    StrategicAsset(
        title="Internal RAG Framework",
        description="Reusable retrieval-augmented generation framework used by 2 product teams. Handles embedding, retrieval, and context assembly.",
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.LOCAL,
        reusability_score=9,
        signaling_strength=6,
        market_relevance=8,
        compounding_potential=8,
        notes="Core reputation asset. Push for executive visibility.",
    ),
    StrategicAsset(
        title="Tech Talk: 'Building Cognitive Systems'",
        description="Presented at internal engineering summit. 85 attendees. Recording shared company-wide.",
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.EXECUTIVE,
        reusability_score=5,
        signaling_strength=9,
        market_relevance=7,
        compounding_potential=6,
        notes="Strong signal event. Plan a follow-up external version.",
    ),
    # Optionality assets
    StrategicAsset(
        title="Second Brain (Cognitive Capture Engine)",
        description="Personal knowledge management system with RAG, classification, entity resolution, and strategic positioning. Python/FastAPI stack.",
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.MARKET,
        portability_score=10,
        market_demand=8,
        monetization_potential=7,
        time_to_deploy=2,
        notes="Highest optionality asset. Fully portable, demonstrates full-stack AI capability.",
    ),
    StrategicAsset(
        title="Embedding Pipeline Expertise",
        description="Deep knowledge of embedding models, vector stores, chunking strategies, and hybrid search. Applicable across industries.",
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.LOCAL,
        portability_score=9,
        market_demand=9,
        monetization_potential=6,
        time_to_deploy=3,
        notes="Hot market skill. Build public artifacts to increase visibility.",
    ),
    StrategicAsset(
        title="Strategic Systems Thinking Framework",
        description="Personal methodology for evaluating projects through authority, leverage, and optionality lenses. Documented in Second Brain.",
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.HIDDEN,
        portability_score=8,
        market_demand=5,
        monetization_potential=8,
        time_to_deploy=4,
        notes="Unique differentiator. Could become a blog series or consulting framework.",
    ),
]


# ── Influence Deltas (weekly tracking) ──────────────────────────

INFLUENCE_DELTAS = [
    InfluenceDelta(
        week_start="2026-02-02",
        advice_sought=True,
        decision_changed=False,
        framing_adopted=False,
        consultation_count=2,
        notes="David asked about embedding model selection. Gave recommendation but no decision yet.",
    ),
    InfluenceDelta(
        week_start="2026-02-09",
        advice_sought=True,
        decision_changed=True,
        framing_adopted=False,
        consultation_count=3,
        notes="Priya adopted my 'build vs buy' framing for the RAG vendor decision. David changed vector DB choice based on my benchmarks.",
    ),
    InfluenceDelta(
        week_start="2026-02-16",
        advice_sought=False,
        decision_changed=False,
        framing_adopted=True,
        consultation_count=1,
        notes="Marcus used 'cognitive system' framing in board deck. Indirect influence through David.",
    ),
    InfluenceDelta(
        week_start="2026-02-23",
        advice_sought=True,
        decision_changed=True,
        framing_adopted=True,
        consultation_count=4,
        notes="Strong week. Tech talk generated multiple follow-up conversations. Ryan's team asking about embedding pipeline collaboration.",
    ),
]


# ── Seed Logic ──────────────────────────────────────────────────

async def seed() -> None:
    """Insert all demo data into the database."""
    settings = get_settings()
    db = Database(settings.resolved_db_path)
    await db.init_db()
    repo = StrategyRepository(db)

    print("Seeding Reputation & Optionality Engine demo data...")
    print()

    # Stakeholders
    for s in STAKEHOLDERS:
        await repo.save_stakeholder(s)
        print(f"  ✓ Stakeholder: {s.name} ({s.role})")

    print()

    # Initiatives
    for i in INITIATIVES:
        await repo.save_initiative(i)
        label = f"{i.scores.total}/25" if i.initiative_type == InitiativeType.SCORED else "mandatory"
        print(f"  ✓ Initiative: {i.title} [{i.category.value}] ({label})")

    print()

    # Assets
    for a in ASSETS:
        await repo.save_asset(a)
        if a.asset_type == AssetCategory.REPUTATION:
            score_label = f"rep={a.reputation_score:.1f}"
        else:
            score_label = f"opt={a.optionality_score:.1f}"
        print(f"  ✓ Asset: {a.title} [{a.asset_type.value}] ({score_label})")

    print()

    # Influence deltas
    for d in INFLUENCE_DELTAS:
        d.delta_score = d.computed_delta
        await repo.save_influence_delta(d)
        print(f"  ✓ Influence: week {d.week_start} (delta={d.delta_score:+d})")

    print()
    print(f"Done! Seeded {len(STAKEHOLDERS)} stakeholders, {len(INITIATIVES)} initiatives,")
    print(f"  {len(ASSETS)} assets, {len(INFLUENCE_DELTAS)} influence records.")
    print()
    print("Start the server and visit http://127.0.0.1:8000/strategy to explore.")


if __name__ == "__main__":
    asyncio.run(seed())
