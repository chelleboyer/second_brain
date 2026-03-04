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
    Friction,
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
        name="CFO",
        role="Chief Financial Officer",
        influence_level=10,
        incentives="Reduce operational risk; predictable costs; avoid downtime; clean audit narratives",
        alignment_score=4,
        dependency_on_you=6,
        trust_score=7,
        notes="Will back modernization if risk + cost are quantified and cutovers are low-drama.",
    ),
    Stakeholder(
        name="VP Operations",
        role="VP of Operations",
        influence_level=9,
        incentives="Store workflow simplicity; fewer exceptions; measurable labor savings; adoption",
        alignment_score=3,
        dependency_on_you=7,
        trust_score=6,
        notes="Cares about manager experience and rollout friction more than technical purity.",
    ),
    Stakeholder(
        name="Director of HR",
        role="HR Director",
        influence_level=7,
        incentives="HRIS cutover with clean data; minimal disruption; correct employee history and payroll feeds",
        alignment_score=3,
        dependency_on_you=5,
        trust_score=6,
        notes="Needs you for data transfer/mapping confidence—especially if historical corrections exist.",
    ),
    Stakeholder(
        name="Infrastructure Lead",
        role="IT Infrastructure Lead",
        influence_level=8,
        incentives="Stability; reduce legacy server footprint; standardize builds; faster restores",
        alignment_score=4,
        dependency_on_you=4,
        trust_score=7,
        notes="Partner for RSS03 retirement planning and cutover runbooks.",
    ),
    Stakeholder(
        name="Procurement Manager",
        role="Procurement / Vendor Management",
        influence_level=6,
        incentives="Vendor onboarding speed; fewer vendor disputes; consistent ordering rules",
        alignment_score=2,
        dependency_on_you=6,
        trust_score=6,
        notes="Key for non-McLane/non-DAS vendor ordering requirements and exceptions.",
    ),
    Stakeholder(
        name="Third-Party Dev Lead",
        role="External Dev Lead (Intranet/Portal)",
        influence_level=6,
        incentives="Clear requirements; fast feedback; stable environments; strong acceptance criteria",
        alignment_score=3,
        dependency_on_you=5,
        trust_score=5,
        notes="Can accelerate delivery if onboarding + boundaries + definition-of-done are crisp.",
    ),
    Stakeholder(
        name="Third-Party Data Partner PM",
        role="External PM (Scan Data Processing)",
        influence_level=6,
        incentives="Stable data contract; clear edge cases; low rework; predictable deliveries",
        alignment_score=3,
        dependency_on_you=5,
        trust_score=5,
        notes="Success depends on your handoff package: schemas, samples, reconciliation rules.",
    ),
        Stakeholder(
        name="CEO",
        role="Chief Executive Officer",
        influence_level=10,
        incentives="Company growth; strategic differentiation; operational resilience; minimal executive surprises",
        alignment_score=4,
        dependency_on_you=5,
        trust_score=7,
        notes="Interested in initiatives that clearly improve operational capability or reduce enterprise risk without creating organizational drag.",
    ),
    Stakeholder(
        name="VP of IT",
        role="Vice President of Information Technology",
        influence_level=9,
        incentives="Delivery of IT initiatives across departments; stable systems; minimal firefighting; successful project outcomes",
        alignment_score=4,
        dependency_on_you=8,
        trust_score=7,
        notes="Often ends up acting as program manager for cross-department initiatives. Your ability to structure work and remove ambiguity is highly leveraged here.",
    ),
    Stakeholder(
        name="COO",
        role="Chief Operating Officer",
        influence_level=10,
        incentives="Operational efficiency; store performance; predictable systems; reduced operational friction",
        alignment_score=3,
        dependency_on_you=6,
        trust_score=6,
        notes="Primary interest is whether systems help or hinder field operations. MOS improvements and ordering automation directly affect this office.",
    ),
    Stakeholder(
        name="CMO",
        role="Chief Marketing Officer",
        influence_level=7,
        incentives="Promotion execution; pricing consistency; merchandising alignment; store presentation",
        alignment_score=3,
        dependency_on_you=4,
        trust_score=5,
        notes="Indirect stakeholder in merchandising systems. Marketing promotions and pricing initiatives eventually depend on accurate item data and ordering flows.",
    )
]

# ── Initiatives ─────────────────────────────────────────────────
INITIATIVES = [
    # Strategic (18+)
    Initiative(
        title="MOS Vendor Expansion (Non-McLane / Non-DAS)",
        description=(
            "Extend Merchandise Ordering System to support non-McLane/non-DAS vendors with "
            "scheduled order generation, manager review/approval, vendor-specific formats "
            "(CSV/EDI/email), and exception handling."
        ),
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
        risk_level=4,
        notes="High business impact. Scope by vendor archetypes first (simple CSV → EDI later).",
    ),
    Initiative(
        title="Intranet/Portal Acceleration via Third-Party Dev Onboarding",
        description=(
            "Onboard a third-party developer/team to accelerate intranet/portal delivery: "
            "environment setup, repo standards, backlog slicing, acceptance criteria, "
            "release cadence, and guardrails for security + data access."
        ),
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=4,
            asymmetric_info=3,
            future_mobility=3,
            reusable_leverage=5,
            right_visibility=4,
        ),
        category=InitiativeCategory.STRATEGIC,
        visibility=VisibilityLevel.EXECUTIVE,
        risk_level=3,
        notes="Leverage play: you become multiplier instead of bottleneck. Protect your core systems with boundaries.",
    ),

    # Supportive (12–17)
    Initiative(
        title="Scan Data Handoff to Third Party (POS → Processing Contract)",
        description=(
            "Package POS scan data for third-party processing: file formats, data dictionary, "
            "discount/qualification rules, reconciliation checks, and an exception workflow "
            "for ambiguous matches."
        ),
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=4,
            asymmetric_info=5,
            future_mobility=3,
            reusable_leverage=4,
            right_visibility=2,
        ),
        category=InitiativeCategory.SUPPORTIVE,
        visibility=VisibilityLevel.LOCAL,
        risk_level=4,
        notes="Reduce rework by over-communicating edge cases + providing a gold standard sample corpus.",
    ),
    Initiative(
        title="HRIS Migration: Data Transfer Support + Validation",
        description=(
            "Support HRIS migration by building transfer mappings, export/import routines, "
            "validation queries, and reconciliation reports for employee/job/pay history."
        ),
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=3,
            asymmetric_info=3,
            future_mobility=2,
            reusable_leverage=3,
            right_visibility=2,
        ),
        category=InitiativeCategory.SUPPORTIVE,
        visibility=VisibilityLevel.LOCAL,
        risk_level=3,
        notes="Make it boring: mapping workbook + repeatable validation scripts + sign-off checkpoints.",
    ),

    # Maintenance (<12)
    Initiative(
        title="RSS03 SQL Server Retirement (Migrate + Decommission)",
        description=(
            "Retire RSS03 SQL Server by inventorying dependencies, migrating databases/jobs, "
            "validating downstream integrations, and executing a low-downtime cutover with rollback."
        ),
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=2,
            asymmetric_info=2,
            future_mobility=1,
            reusable_leverage=2,
            right_visibility=1,
        ),
        category=InitiativeCategory.MAINTENANCE,
        visibility=VisibilityLevel.HIDDEN,
        risk_level=5,
        notes="High risk but low visibility—use a crisp runbook and get explicit sign-off on the cutover window.",
    ),
]

# ── Strategic Assets ────────────────────────────────────────────
ASSETS = [
    # Reputation assets
    StrategicAsset(
        title="MOS Vendor Archetype Playbook (Non-McLane/Non-DAS)",
        description=(
            "Playbook defining vendor onboarding archetypes (simple CSV, portal download, EDI, email-only), "
            "required fields, lead times, pack/UM rules, and exception handling patterns."
        ),
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.EXECUTIVE,
        reusability_score=9,
        signaling_strength=7,
        market_relevance=6,
        compounding_potential=8,
        notes="Turns vendor chaos into a reusable onboarding machine.",
    ),
    StrategicAsset(
        title="MOS Ordering Workflow ADR Set",
        description=(
            "Architecture decision records for MOS ordering: line-level changes, status model, approvals, "
            "scheduled generation, vendor cutoffs, and audit-friendly change logs."
        ),
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.LOCAL,
        reusability_score=8,
        signaling_strength=6,
        market_relevance=6,
        compounding_potential=9,
        notes="Each new vendor becomes easier because decisions are already documented.",
    ),
    StrategicAsset(
        title="Scan Data Third-Party Handoff Package (Contract + Samples)",
        description=(
            "Complete handoff kit: schema/data dictionary, sample extracts, edge-case catalog, "
            "reconciliation checklist, and exception workflow for ambiguous transactions."
        ),
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.LOCAL,
        reusability_score=7,
        signaling_strength=6,
        market_relevance=5,
        compounding_potential=7,
        notes="Prevents 'it’s your data' blame ping-pong. Makes integration measurable.",
    ),
    StrategicAsset(
        title="RSS03 Dependency Inventory + Cutover Runbook",
        description=(
            "Inventory of RSS03 databases, SQL Agent jobs, linked servers, SSIS packages, "
            "application connection strings, and reporting dependencies—plus cutover/rollback steps."
        ),
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.LOCAL,
        reusability_score=6,
        signaling_strength=5,
        market_relevance=5,
        compounding_potential=6,
        notes="Boring artifact, but it saves weekends.",
    ),
    StrategicAsset(
        title="HRIS Migration Mapping Workbook + Validation Queries",
        description=(
            "Field-by-field HRIS mapping workbook with transformation rules, "
            "SQL validation queries, row count checks, and exception reports for missing/invalid values."
        ),
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.EXECUTIVE,
        reusability_score=6,
        signaling_strength=7,
        market_relevance=5,
        compounding_potential=6,
        notes="Makes HR trust the cutover—and makes IT look competent, which is refreshing.",
    ),
    StrategicAsset(
        title="Third-Party Dev Onboarding Kit (Portal/Intranet)",
        description=(
            "Onboarding kit for external devs: repo conventions, local/dev/stage setup, "
            "branching/release process, coding standards, acceptance criteria templates, and demo cadence."
        ),
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.EXECUTIVE,
        reusability_score=9,
        signaling_strength=8,
        market_relevance=6,
        compounding_potential=8,
        notes="This is how you scale a 1–2 person team without summoning chaos.",
    ),

    # Optionality assets
    StrategicAsset(
        title="Enterprise Integrations Master Map (POS ↔ ERP ↔ Intranet)",
        description=(
            "Living map of core enterprise integrations: where data originates, transforms, and lands "
            "(POS, ERP, HRIS, vendor ordering, reporting). Includes ownership and failure modes."
        ),
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.LOCAL,
        portability_score=8,
        market_demand=8,
        monetization_potential=6,
        time_to_deploy=3,
        notes="Portable systems-thinking asset; valuable for any multi-system retail enterprise.",
    ),
    StrategicAsset(
        title="Repeatable Data Handoff Patterns (Schemas, Samples, Reconciliation)",
        description=(
            "Reusable pattern library for giving data to third parties: contracts, sample corpora, "
            "validation queries, and reconciliation dashboards."
        ),
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.MARKET,
        portability_score=9,
        market_demand=7,
        monetization_potential=7,
        time_to_deploy=2,
        notes="Turns one-off integrations into a reusable capability.",
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
        notes="Ops asked how to expand MOS ordering beyond McLane/DAS without blowing up store workflow. I proposed vendor archetypes + phased rollout.",
    ),
    InfluenceDelta(
        week_start="2026-02-09",
        advice_sought=True,
        decision_changed=True,
        framing_adopted=True,
        consultation_count=4,
        notes="CFO adopted my 'reduce vendor friction + quantify downtime risk' framing for RSS03 retirement and approved time for dependency inventory.",
    ),
    InfluenceDelta(
        week_start="2026-02-16",
        advice_sought=True,
        decision_changed=True,
        framing_adopted=False,
        consultation_count=3,
        notes="HR Director asked for HRIS transfer help; we agreed on mapping workbook + automated validations + sign-off checkpoints.",
    ),
    InfluenceDelta(
        week_start="2026-02-23",
        advice_sought=True,
        decision_changed=True,
        framing_adopted=True,
        consultation_count=5,
        notes="Third-party dev onboarding plan changed: moved to weekly demo cadence + explicit acceptance criteria + tighter environment guardrails. External dev lead aligned.",
    ),
    InfluenceDelta(
        week_start="2026-03-02",
        advice_sought=True,
        decision_changed=False,
        framing_adopted=True,
        consultation_count=4,
        notes="Scan data partner PM adopted my 'data contract + reconciliation first' framing; we prioritized sample corpus + edge-case catalog before scaling feeds.",
    ),
]

# ── Frictions ────────────────────────────────────────────────────────────────

FRICTIONS = [
    Friction(
        title="Vendor ordering fragmentation (non-McLane / non-DAS)",
        description="Each vendor has different rules, lead times, order formats, minimums, and exception handling—stores absorb the complexity.",
        category="Operations",
        severity=5,
        frequency=5,
        blast_radius=4,
        owner_role="Procurement / IT",
        affected_stakeholders=["COO", "VP Operations", "Procurement Manager", "Store Managers"],
        related_initiatives=["MOS Vendor Expansion (Non-McLane / Non-DAS)"],
        signals=[
            "Managers spend time on manual vendor portals/emails",
            "Frequent vendor disputes about quantities/lead times",
            "Stockouts or over-ordering for niche vendors",
        ],
        countermeasures=[
            "Vendor archetypes + standard contract fields",
            "Automated scheduled order generation + review",
            "Exception workflow with reason codes",
        ],
        notes="Start with the top 3–5 non-McLane/non-DAS vendors by pain, not by political visibility.",
    ),
    Friction(
        title="Ambiguous discount-to-item matching in POS scan data",
        description="Discount lines sometimes apply to multiple items but appear associated to one item, creating reconciliation and trust issues.",
        category="Data Quality",
        severity=5,
        frequency=4,
        blast_radius=4,
        owner_role="IT / Data",
        affected_stakeholders=["VP of IT", "Third-Party Data Partner PM", "CFO"],
        related_initiatives=["Scan Data Handoff to Third Party (POS → Processing Contract)"],
        signals=[
            "Unexplained variances between expected and actual discount totals",
            "High manual review time for exceptions",
            "Partner rejects batches due to inconsistencies",
        ],
        countermeasures=[
            "Deterministic matching heuristic + confidence scoring",
            "Gold-standard sample corpus and edge-case catalog",
            "Quarantine ambiguous transactions + review workflow",
        ],
        notes="Treat this like a product: publish a 'data contract' and a partner-facing reconciliation checklist.",
    ),
    Friction(
        title="Data handoff churn with third parties (schema drift + unclear contracts)",
        description="Without a hard data contract, small changes create rework, blame loops, and missed timelines.",
        category="Delivery",
        severity=4,
        frequency=4,
        blast_radius=4,
        owner_role="IT / PM",
        affected_stakeholders=["VP of IT", "Third-Party Data Partner PM", "CFO"],
        related_initiatives=["Scan Data Handoff to Third Party (POS → Processing Contract)"],
        signals=[
            "Repeated partner questions about field meaning",
            "Batch failures after 'minor' internal changes",
            "No single source of truth for schemas and examples",
        ],
        countermeasures=[
            "Versioned schema + data dictionary",
            "Signed-off sample files per version",
            "Automated validation + reconciliation report",
        ],
        notes="If it isn’t versioned, it isn’t real.",
    ),
    Friction(
        title="Legacy SQL Server RSS03 dependency unknowns",
        description="Critical jobs, integrations, or reports may depend on RSS03 in undocumented ways, making retirement risky.",
        category="Infrastructure",
        severity=5,
        frequency=3,
        blast_radius=5,
        owner_role="Infrastructure / IT",
        affected_stakeholders=["Infrastructure Lead", "VP of IT", "CFO"],
        related_initiatives=["RSS03 SQL Server Retirement (Migrate + Decommission)"],
        signals=[
            "Restore/migration attempts reveal unknown connections",
            "Apps reference old connection strings",
            "SQL Agent jobs with unclear owners",
        ],
        countermeasures=[
            "Dependency inventory + ownership mapping",
            "Cutover runbook + rollback plan",
            "Freeze window + sign-off checkpoint",
        ],
        notes="This is a classic 'invisible cliff'—high risk, low applause.",
    ),
    Friction(
        title="Cross-department initiatives default to VP of IT as PM",
        description="When ownership is unclear, the VP of IT ends up project-managing everything, slowing delivery and creating bottlenecks.",
        category="Org Design",
        severity=4,
        frequency=5,
        blast_radius=4,
        owner_role="Executive Team",
        affected_stakeholders=["VP of IT", "CEO", "COO", "CFO"],
        related_initiatives=["Intranet/Portal Acceleration via Third-Party Dev Onboarding"],
        signals=[
            "Decisions stall waiting for IT triage",
            "Backlog whiplash; priorities change weekly",
            "VP of IT becomes the status-update bus",
        ],
        countermeasures=[
            "Explicit RACI per initiative",
            "Definition-of-done + acceptance criteria per story",
            "Weekly demo cadence with decision log",
        ],
        notes="You’re not just onboarding a dev—you’re onboarding a delivery system.",
    ),
    Friction(
        title="Intranet/portal delivery drag (unclear scope + slow feedback loops)",
        description="Portal work expands endlessly; without tight slices and demos, progress feels invisible and stakeholders lose confidence.",
        category="Delivery",
        severity=4,
        frequency=4,
        blast_radius=3,
        owner_role="IT / Business Owners",
        affected_stakeholders=["VP of IT", "CEO", "COO", "CMO"],
        related_initiatives=["Intranet/Portal Acceleration via Third-Party Dev Onboarding"],
        signals=[
            "Stakeholders say 'this isn't what I meant' late in the sprint",
            "Large stories that never reach done",
            "Long time between usable releases",
        ],
        countermeasures=[
            "Backlog slicing into 1-week shippable increments",
            "Weekly demos + recorded walkthroughs",
            "UI standards + component library early",
        ],
        notes="Nothing builds trust like shipping.",
    ),
    Friction(
        title="HRIS migration data ambiguity (history, corrections, and mapping edge cases)",
        description="Employee/job/pay history contains exceptions; bad mappings create long-lived HR and payroll pain.",
        category="Data Migration",
        severity=5,
        frequency=3,
        blast_radius=4,
        owner_role="HR / IT",
        affected_stakeholders=["Director of HR", "VP of IT", "CFO"],
        related_initiatives=["HRIS Migration: Data Transfer Support + Validation"],
        signals=[
            "Duplicate employees or conflicting identifiers",
            "Missing effective dates or invalid job codes",
            "Unexpected payroll variances after test loads",
        ],
        countermeasures=[
            "Mapping workbook with transformation rules",
            "Automated validation queries + reconciliation reports",
            "Sign-off gates: HR validates samples before full load",
        ],
        notes="Make a 'known exceptions' table and treat it like a product backlog.",
    ),
    Friction(
        title="Single-dev-team throughput constraints (context switching tax)",
        description="One or two developers handling ops + projects causes constant context switching and unpredictable throughput.",
        category="Capacity",
        severity=4,
        frequency=5,
        blast_radius=4,
        owner_role="IT Leadership",
        affected_stakeholders=["VP of IT", "CEO", "COO"],
        related_initiatives=["Intranet/Portal Acceleration via Third-Party Dev Onboarding", "MOS Vendor Expansion (Non-McLane / Non-DAS)"],
        signals=[
            "Long lead time for small changes",
            "Frequent interruptions for production support",
            "Projects stall during incident weeks",
        ],
        countermeasures=[
            "Dedicated support windows + rotating on-call",
            "Third-party dev augmentation with guardrails",
            "Strict WIP limits and release cadence",
        ],
        notes="Throughput is a system property, not a motivation problem. (Unfortunately.)",
    ),
    Friction(
        title="Store-facing workflow friction (too many clicks, too many exceptions)",
        description="If store managers have to fight the workflow, adoption collapses—especially for ordering and approvals.",
        category="UX / Adoption",
        severity=4,
        frequency=5,
        blast_radius=5,
        owner_role="Ops / IT",
        affected_stakeholders=["COO", "VP Operations", "Store Managers"],
        related_initiatives=["MOS Vendor Expansion (Non-McLane / Non-DAS)"],
        signals=[
            "Managers bypass the system with phone calls/emails",
            "Approval delays cause missed vendor cutoff times",
            "High variance in ordering behaviors across stores",
        ],
        countermeasures=[
            "Default paths for 80% use cases",
            "Exception reasons instead of freeform notes",
            "Role-based views with minimal fields",
        ],
        notes="Every extra click is a tiny rebellion.",
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

    # Frictions
    for f in FRICTIONS:
        await repo.save_friction(f)
        print(f"  ✓ Friction: {f.title} [{f.category}] (impact={f.impact_score:.1f})")

    print()
    print(f"Done! Seeded {len(STAKEHOLDERS)} stakeholders, {len(INITIATIVES)} initiatives,")
    print(f"  {len(ASSETS)} assets, {len(INFLUENCE_DELTAS)} influence records,")
    print(f"  {len(FRICTIONS)} frictions.")
    print()
    print("Start the server and visit http://127.0.0.1:8000/strategy to explore.")


if __name__ == "__main__":
    asyncio.run(seed())
