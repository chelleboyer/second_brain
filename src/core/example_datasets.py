"""Example datasets for the Reputation & Optionality Engine.

Provides pre-built datasets that can be loaded via the UI or CLI.
Each dataset is a collection of stakeholders, initiatives, assets,
and influence deltas designed around a specific persona.
"""

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
from src.storage.strategy_repository import StrategyRepository

import structlog

log = structlog.get_logger()


# ═══════════════════════════════════════════════════════════════════
# Dataset: Corporate Engineer
# ═══════════════════════════════════════════════════════════════════

CORPORATE_STAKEHOLDERS = [
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

CORPORATE_INITIATIVES = [
    Initiative(
        title="AI-Native Architecture Blueprint",
        description="Design and publish the company-wide reference architecture for AI-native services.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(authority=5, asymmetric_info=4, future_mobility=4, reusable_leverage=5, right_visibility=4),
        category=InitiativeCategory.STRATEGIC,
        visibility=VisibilityLevel.EXECUTIVE,
        risk_level=2,
        notes="Positions you as the AI architecture authority.",
    ),
    Initiative(
        title="Second Brain Open-Source Release",
        description="Package the cognitive capture engine as an open-source project.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(authority=4, asymmetric_info=3, future_mobility=5, reusable_leverage=5, right_visibility=5),
        category=InitiativeCategory.STRATEGIC,
        visibility=VisibilityLevel.MARKET,
        risk_level=3,
        notes="High optionality value. Requires IP review before publishing.",
    ),
    Initiative(
        title="RAG Retrieval Quality Improvements",
        description="Improve recall@10 by 15% through hybrid search and re-ranking.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(authority=3, asymmetric_info=3, future_mobility=3, reusable_leverage=3, right_visibility=2),
        category=InitiativeCategory.SUPPORTIVE,
        visibility=VisibilityLevel.LOCAL,
        risk_level=1,
    ),
    Initiative(
        title="Engineering Onboarding Playbook",
        description="Create a structured onboarding playbook for new engineers.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(authority=3, asymmetric_info=1, future_mobility=2, reusable_leverage=4, right_visibility=3),
        category=InitiativeCategory.SUPPORTIVE,
        visibility=VisibilityLevel.LOCAL,
        risk_level=1,
    ),
    Initiative(
        title="CI Pipeline Maintenance",
        description="Keep CI green: fix flaky tests, update dependencies.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(authority=1, asymmetric_info=0, future_mobility=1, reusable_leverage=1, right_visibility=1),
        category=InitiativeCategory.MAINTENANCE,
        visibility=VisibilityLevel.HIDDEN,
        risk_level=1,
    ),
    Initiative(
        title="Quarterly Security Patches",
        description="Apply dependency security patches, rotate credentials.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(authority=1, asymmetric_info=1, future_mobility=0, reusable_leverage=0, right_visibility=0),
        category=InitiativeCategory.MAINTENANCE,
        visibility=VisibilityLevel.HIDDEN,
        risk_level=2,
    ),
    Initiative(
        title="Platform Incident Response",
        description="On-call rotation and incident response for AI platform services.",
        initiative_type=InitiativeType.MANDATORY,
        scores=InitiativeScores(),
        category=InitiativeCategory.MAINTENANCE,
        visibility=VisibilityLevel.LOCAL,
        risk_level=3,
    ),
]

CORPORATE_ASSETS = [
    StrategicAsset(
        title="AI Architecture Decision Records",
        description="Collection of 12 ADRs documenting AI system design decisions.",
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.EXECUTIVE,
        reusability_score=8, signaling_strength=7, market_relevance=6, compounding_potential=9,
    ),
    StrategicAsset(
        title="Internal RAG Framework",
        description="Reusable retrieval-augmented generation framework used by 2 product teams.",
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.LOCAL,
        reusability_score=9, signaling_strength=6, market_relevance=8, compounding_potential=8,
    ),
    StrategicAsset(
        title="Tech Talk: 'Building Cognitive Systems'",
        description="Presented at internal engineering summit. 85 attendees.",
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.EXECUTIVE,
        reusability_score=5, signaling_strength=9, market_relevance=7, compounding_potential=6,
    ),
    StrategicAsset(
        title="Second Brain (Cognitive Capture Engine)",
        description="Personal knowledge management system with RAG, classification, and strategic positioning.",
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.MARKET,
        portability_score=10, market_demand=8, monetization_potential=7, time_to_deploy=2,
    ),
    StrategicAsset(
        title="Embedding Pipeline Expertise",
        description="Deep knowledge of embedding models, vector stores, and hybrid search.",
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.LOCAL,
        portability_score=9, market_demand=9, monetization_potential=6, time_to_deploy=3,
    ),
    StrategicAsset(
        title="Strategic Systems Thinking Framework",
        description="Personal methodology for evaluating projects through authority and leverage lenses.",
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.HIDDEN,
        portability_score=8, market_demand=5, monetization_potential=8, time_to_deploy=4,
    ),
]

CORPORATE_INFLUENCE = [
    InfluenceDelta(
        week_start="2026-02-02",
        advice_sought=True, decision_changed=False, framing_adopted=False,
        consultation_count=2,
        notes="David asked about embedding model selection.",
    ),
    InfluenceDelta(
        week_start="2026-02-09",
        advice_sought=True, decision_changed=True, framing_adopted=False,
        consultation_count=3,
        notes="Priya adopted my 'build vs buy' framing for the RAG vendor decision.",
    ),
    InfluenceDelta(
        week_start="2026-02-16",
        advice_sought=False, decision_changed=False, framing_adopted=True,
        consultation_count=1,
        notes="Marcus used 'cognitive system' framing in board deck.",
    ),
    InfluenceDelta(
        week_start="2026-02-23",
        advice_sought=True, decision_changed=True, framing_adopted=True,
        consultation_count=4,
        notes="Strong week. Tech talk generated multiple follow-up conversations.",
    ),
]


# ═══════════════════════════════════════════════════════════════════
# Dataset: Personal Second Brain
# ═══════════════════════════════════════════════════════════════════

PERSONAL_STAKEHOLDERS = [
    Stakeholder(
        name="Alex (Mentor)",
        role="Industry Mentor",
        influence_level=8,
        incentives="Enjoy mentoring; expand own network; stay current on trends",
        alignment_score=4,
        dependency_on_you=2,
        trust_score=9,
        notes="Monthly calls. Gives honest feedback on career direction. Intro'd me to 3 key contacts.",
    ),
    Stakeholder(
        name="Sam (Freelance Partner)",
        role="Design Collaborator",
        influence_level=5,
        incentives="Quality projects; portfolio pieces; reliable income",
        alignment_score=3,
        dependency_on_you=6,
        trust_score=8,
        notes="We've shipped 4 projects together. I handle strategy and dev, Sam handles design and UX.",
    ),
    Stakeholder(
        name="Jordan (Newsletter Audience)",
        role="Online Community",
        influence_level=4,
        incentives="Learn practical skills; get curated resources; stay ahead",
        alignment_score=2,
        dependency_on_you=7,
        trust_score=6,
        notes="~800 subscribers. Engagement rate 45%. They share my content, which drives inbound leads.",
    ),
    Stakeholder(
        name="Casey (Accountability Partner)",
        role="Peer Creator",
        influence_level=5,
        incentives="Mutual accountability; idea cross-pollination; shared audience growth",
        alignment_score=4,
        dependency_on_you=4,
        trust_score=9,
        notes="Weekly check-ins. We review each other's drafts and share audience insights.",
    ),
    Stakeholder(
        name="Taylor (Past Client)",
        role="Agency Founder",
        influence_level=7,
        incentives="Quality vendor relationships; thought leadership content; competitive edge",
        alignment_score=1,
        dependency_on_you=3,
        trust_score=7,
        notes="Sent 2 referrals last quarter. Could become ongoing retainer if I pitch the automation project.",
    ),
]

PERSONAL_INITIATIVES = [
    # Strategic (18+)
    Initiative(
        title="Launch AI Productivity Newsletter",
        description="Weekly newsletter on practical AI workflows for knowledge workers. Build audience, establish thought leadership, create lead funnel for consulting.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=5,
            asymmetric_info=4,
            future_mobility=5,
            reusable_leverage=5,
            right_visibility=5,
        ),
        category=InitiativeCategory.STRATEGIC,
        visibility=VisibilityLevel.MARKET,
        risk_level=1,
        notes="Highest leverage move. Every issue compounds: audience, credibility, and searchable content.",
    ),
    Initiative(
        title="Build & Ship Personal Knowledge Tool",
        description="Open-source a polished version of my second brain system. Demonstrates technical ability, creates inbound interest, and generates portfolio artifact.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=4,
            asymmetric_info=4,
            future_mobility=5,
            reusable_leverage=4,
            right_visibility=4,
        ),
        category=InitiativeCategory.STRATEGIC,
        visibility=VisibilityLevel.MARKET,
        risk_level=2,
        notes="Ship MVP, then iterate publicly. Document the build process as content.",
    ),
    # Supportive (12–17)
    Initiative(
        title="Create Reusable Project Starter Templates",
        description="Package my common project setups (FastAPI + HTMX, Python CLI, data pipeline) as public starter templates on GitHub.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=3,
            asymmetric_info=2,
            future_mobility=3,
            reusable_leverage=4,
            right_visibility=3,
        ),
        category=InitiativeCategory.SUPPORTIVE,
        visibility=VisibilityLevel.MARKET,
        risk_level=1,
        notes="Low effort, high reuse. Each template saves me 4-6 hours on new projects.",
    ),
    Initiative(
        title="Write 'Systems Thinking for Solopreneurs' Blog Series",
        description="5-part blog series applying systems thinking to solo business operations. Covers decision frameworks, feedback loops, and leverage.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=4,
            asymmetric_info=2,
            future_mobility=2,
            reusable_leverage=3,
            right_visibility=3,
        ),
        category=InitiativeCategory.SUPPORTIVE,
        visibility=VisibilityLevel.MARKET,
        risk_level=1,
        notes="Positions me as a thinker, not just a builder. Good for attracting consulting leads.",
    ),
    Initiative(
        title="Automate Client Reporting Pipeline",
        description="Build automated weekly report generation for freelance clients. Saves 3 hours/week and impresses clients with polish.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=2,
            asymmetric_info=2,
            future_mobility=2,
            reusable_leverage=4,
            right_visibility=2,
        ),
        category=InitiativeCategory.SUPPORTIVE,
        visibility=VisibilityLevel.LOCAL,
        risk_level=1,
        notes="Good leverage play — reclaim time and raise perceived professionalism.",
    ),
    # Maintenance (<12)
    Initiative(
        title="Bookkeeping & Invoicing",
        description="Monthly bookkeeping, send invoices, reconcile expenses, prep for quarterly taxes.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=0,
            asymmetric_info=0,
            future_mobility=1,
            reusable_leverage=1,
            right_visibility=0,
        ),
        category=InitiativeCategory.MAINTENANCE,
        visibility=VisibilityLevel.HIDDEN,
        risk_level=2,
        notes="Non-negotiable. Block 2 hours on the 1st of each month and don't think about it.",
    ),
    Initiative(
        title="Website & Portfolio Updates",
        description="Keep personal site current: update project list, fix broken links, refresh testimonials.",
        initiative_type=InitiativeType.SCORED,
        scores=InitiativeScores(
            authority=1,
            asymmetric_info=0,
            future_mobility=1,
            reusable_leverage=0,
            right_visibility=1,
        ),
        category=InitiativeCategory.MAINTENANCE,
        visibility=VisibilityLevel.HIDDEN,
        risk_level=1,
        notes="Quick quarterly pass. Don't over-invest in design — content matters more.",
    ),
    # Mandatory
    Initiative(
        title="Active Client Deliverables",
        description="Ongoing freelance project work for current clients. Core revenue stream.",
        initiative_type=InitiativeType.MANDATORY,
        scores=InitiativeScores(),
        category=InitiativeCategory.MAINTENANCE,
        visibility=VisibilityLevel.LOCAL,
        risk_level=2,
        notes="Revenue-critical. Turn great delivery into case studies and testimonials.",
    ),
]

PERSONAL_ASSETS = [
    # Reputation assets
    StrategicAsset(
        title="Personal Blog (35 posts)",
        description="Technical blog covering AI workflows, Python tooling, and knowledge management. 2,500 monthly visitors, 3 posts ranking on first page of Google.",
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.MARKET,
        reusability_score=8,
        signaling_strength=7,
        market_relevance=8,
        compounding_potential=9,
        notes="Each new post reinforces authority and drives long-tail search traffic. Highest compounding asset.",
    ),
    StrategicAsset(
        title="GitHub Portfolio (12 public repos)",
        description="Mix of tools, starter templates, and open-source contributions. 340 combined stars. Pinned repos get regular traffic.",
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.MARKET,
        reusability_score=7,
        signaling_strength=6,
        market_relevance=7,
        compounding_potential=7,
        notes="Stars and forks serve as social proof. Keep pinned repos polished.",
    ),
    StrategicAsset(
        title="Client Case Studies (4 published)",
        description="Detailed write-ups of past projects with quantified outcomes. Used in proposals and shared on LinkedIn.",
        asset_type=AssetCategory.REPUTATION,
        visibility=VisibilityLevel.MARKET,
        reusability_score=9,
        signaling_strength=8,
        market_relevance=7,
        compounding_potential=6,
        notes="Most persuasive sales asset. Add one per quarter from best client work.",
    ),
    # Optionality assets
    StrategicAsset(
        title="Second Brain System",
        description="Full-stack knowledge management system with AI classification, entity resolution, and strategic positioning engine. Fully portable.",
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.MARKET,
        portability_score=10,
        market_demand=8,
        monetization_potential=8,
        time_to_deploy=2,
        notes="Can demo in any interview, sell as SaaS, or use as consulting proof-of-concept.",
    ),
    StrategicAsset(
        title="AI Automation Playbook",
        description="Personal collection of tested AI automation patterns: document processing, email triage, content generation, data extraction.",
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.HIDDEN,
        portability_score=9,
        market_demand=9,
        monetization_potential=7,
        time_to_deploy=3,
        notes="Package as a paid course or consulting offering. High market demand right now.",
    ),
    StrategicAsset(
        title="Freelance Client Network",
        description="Warm relationships with 8 past clients across 4 industries. 3 are repeat clients, 2 send regular referrals.",
        asset_type=AssetCategory.OPTIONALITY,
        visibility=VisibilityLevel.LOCAL,
        portability_score=8,
        market_demand=6,
        monetization_potential=9,
        time_to_deploy=1,
        notes="Most immediate revenue asset. Nurture with quarterly check-ins and useful content.",
    ),
]

PERSONAL_INFLUENCE = [
    InfluenceDelta(
        week_start="2026-02-02",
        advice_sought=True,
        decision_changed=False,
        framing_adopted=False,
        consultation_count=1,
        notes="Mentor asked my opinion on a tool recommendation for one of their mentees. Newsletter got 2 reply-alls from readers.",
    ),
    InfluenceDelta(
        week_start="2026-02-09",
        advice_sought=False,
        decision_changed=True,
        framing_adopted=False,
        consultation_count=2,
        notes="Taylor's agency adopted my automation approach for their client reporting. New subscriber said they found me through a retweet.",
    ),
    InfluenceDelta(
        week_start="2026-02-16",
        advice_sought=True,
        decision_changed=False,
        framing_adopted=True,
        consultation_count=3,
        notes="Casey started using my 'optionality scoring' framework for their own projects. LinkedIn post got 1,200 impressions.",
    ),
    InfluenceDelta(
        week_start="2026-02-23",
        advice_sought=True,
        decision_changed=True,
        framing_adopted=True,
        consultation_count=3,
        notes="Best week yet. Blog post shared by a micro-influencer in the AI space. 2 inbound consulting inquiries from strangers.",
    ),
]


# ═══════════════════════════════════════════════════════════════════
# Dataset Registry & Loader
# ═══════════════════════════════════════════════════════════════════

DATASETS = {
    "corporate": {
        "label": "Corporate Engineer",
        "description": "A senior engineer navigating corporate influence, visibility, and career positioning.",
        "stakeholders": CORPORATE_STAKEHOLDERS,
        "initiatives": CORPORATE_INITIATIVES,
        "assets": CORPORATE_ASSETS,
        "influence": CORPORATE_INFLUENCE,
    },
    "personal": {
        "label": "Personal / Solopreneur",
        "description": "A freelancer and creator building audience, shipping side projects, and growing consulting revenue.",
        "stakeholders": PERSONAL_STAKEHOLDERS,
        "initiatives": PERSONAL_INITIATIVES,
        "assets": PERSONAL_ASSETS,
        "influence": PERSONAL_INFLUENCE,
    },
}


async def load_example_dataset(
    repo: StrategyRepository,
    dataset_key: str,
    clear_existing: bool = True,
) -> dict[str, int]:
    """Load an example dataset into the strategy repository.

    Args:
        repo: Strategy repository instance.
        dataset_key: Key from DATASETS ('corporate' or 'personal').
        clear_existing: If True, delete all existing strategy data first.

    Returns:
        Dict with counts of loaded entities.
    """
    if dataset_key not in DATASETS:
        raise ValueError(f"Unknown dataset: {dataset_key}. Available: {list(DATASETS.keys())}")

    dataset = DATASETS[dataset_key]
    log.info("loading_example_dataset", dataset=dataset_key, clear=clear_existing)

    if clear_existing:
        await _clear_all_strategy_data(repo)

    counts: dict[str, int] = {}

    # Stakeholders
    for s in dataset["stakeholders"]:
        await repo.save_stakeholder(s)
    counts["stakeholders"] = len(dataset["stakeholders"])

    # Initiatives
    for i in dataset["initiatives"]:
        await repo.save_initiative(i)
    counts["initiatives"] = len(dataset["initiatives"])

    # Assets
    for a in dataset["assets"]:
        await repo.save_asset(a)
    counts["assets"] = len(dataset["assets"])

    # Influence deltas
    for d in dataset["influence"]:
        d.delta_score = d.computed_delta
        await repo.save_influence_delta(d)
    counts["influence_deltas"] = len(dataset["influence"])

    log.info("example_dataset_loaded", dataset=dataset_key, counts=counts)
    return counts


async def _clear_all_strategy_data(repo: StrategyRepository) -> None:
    """Remove all strategy data from the database."""
    async with repo.db.get_connection() as conn:
        await conn.execute("DELETE FROM weekly_simulations")
        await conn.execute("DELETE FROM influence_deltas")
        await conn.execute("DELETE FROM initiative_links")
        await conn.execute("DELETE FROM strategic_assets")
        await conn.execute("DELETE FROM initiatives")
        await conn.execute("DELETE FROM stakeholders")
        await conn.commit()
    log.info("strategy_data_cleared")
