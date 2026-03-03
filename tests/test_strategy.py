"""Tests for Phase II: Strategic Positioning Engine."""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.models.enums import (
    AssetCategory,
    InitiativeCategory,
    InitiativeType,
    VisibilityLevel,
)
from src.models.strategy import (
    InfluenceDelta,
    InfluenceDeltaCreate,
    Initiative,
    InitiativeCreate,
    InitiativeLink,
    InitiativeScores,
    Stakeholder,
    StakeholderCreate,
    StrategicAsset,
    StrategicAssetCreate,
    WeeklySimulation,
)
from src.storage.database import Database
from src.storage.strategy_repository import StrategyRepository
from src.core.evaluation import MoveEvaluationEngine
from src.core.simulation import InfluenceTracker, StrategicSimulator


# ── Fixtures ─────────────────────────────────────────────────────

@pytest.fixture
async def strategy_db() -> AsyncGenerator[Database, None]:
    """In-memory SQLite database with schema initialized."""
    database = Database(":memory:")
    await database.init_db()
    yield database


@pytest.fixture
async def strategy_repo(strategy_db: Database) -> StrategyRepository:
    return StrategyRepository(strategy_db)


@pytest.fixture
async def evaluation_engine(strategy_repo: StrategyRepository) -> MoveEvaluationEngine:
    return MoveEvaluationEngine(strategy_repo)


@pytest.fixture
async def influence_tracker(strategy_repo: StrategyRepository) -> InfluenceTracker:
    return InfluenceTracker(strategy_repo)


@pytest.fixture
async def simulator(
    strategy_repo: StrategyRepository,
    influence_tracker: InfluenceTracker,
) -> StrategicSimulator:
    return StrategicSimulator(
        strategy_repo=strategy_repo,
        influence_tracker=influence_tracker,
        provider=None,  # No LLM for tests
    )


# ── Model Tests ──────────────────────────────────────────────────

class TestInitiativeScores:
    """Tests for the InitiativeScores model."""

    def test_total_calculation(self):
        scores = InitiativeScores(
            authority=3, asymmetric_info=4, future_mobility=5,
            reusable_leverage=3, right_visibility=4,
        )
        assert scores.total == 19

    def test_total_zero(self):
        scores = InitiativeScores()
        assert scores.total == 0

    def test_total_max(self):
        scores = InitiativeScores(
            authority=5, asymmetric_info=5, future_mobility=5,
            reusable_leverage=5, right_visibility=5,
        )
        assert scores.total == 25

    def test_category_strategic(self):
        scores = InitiativeScores(
            authority=4, asymmetric_info=4, future_mobility=4,
            reusable_leverage=3, right_visibility=4,
        )
        assert scores.category == InitiativeCategory.STRATEGIC

    def test_category_supportive(self):
        scores = InitiativeScores(
            authority=3, asymmetric_info=3, future_mobility=2,
            reusable_leverage=2, right_visibility=3,
        )
        assert scores.category == InitiativeCategory.SUPPORTIVE

    def test_category_maintenance(self):
        scores = InitiativeScores(
            authority=1, asymmetric_info=2, future_mobility=1,
            reusable_leverage=1, right_visibility=2,
        )
        assert scores.category == InitiativeCategory.MAINTENANCE

    def test_category_boundary_12(self):
        """Score exactly 12 → supportive."""
        scores = InitiativeScores(
            authority=3, asymmetric_info=3, future_mobility=2,
            reusable_leverage=2, right_visibility=2,
        )
        assert scores.total == 12
        assert scores.category == InitiativeCategory.SUPPORTIVE

    def test_category_boundary_18(self):
        """Score exactly 18 → strategic."""
        scores = InitiativeScores(
            authority=4, asymmetric_info=4, future_mobility=4,
            reusable_leverage=3, right_visibility=3,
        )
        assert scores.total == 18
        assert scores.category == InitiativeCategory.STRATEGIC

    def test_category_boundary_11(self):
        """Score 11 → maintenance."""
        scores = InitiativeScores(
            authority=3, asymmetric_info=2, future_mobility=2,
            reusable_leverage=2, right_visibility=2,
        )
        assert scores.total == 11
        assert scores.category == InitiativeCategory.MAINTENANCE


class TestStrategicAsset:
    """Tests for StrategicAsset composite scores."""

    def test_reputation_score(self):
        asset = StrategicAsset(
            title="Test",
            asset_type=AssetCategory.REPUTATION,
            reusability_score=8,
            signaling_strength=6,
            market_relevance=7,
            compounding_potential=9,
        )
        assert asset.reputation_score == 7.5

    def test_optionality_score(self):
        asset = StrategicAsset(
            title="Test",
            asset_type=AssetCategory.OPTIONALITY,
            portability_score=8,
            market_demand=7,
            monetization_potential=6,
            time_to_deploy=2,  # Low = fast = good
        )
        # (8 + 7 + 6 + (10-2)) / 4 = (8+7+6+8)/4 = 29/4 = 7.25
        assert asset.optionality_score == 7.25

    def test_reputation_score_zero(self):
        asset = StrategicAsset(title="Empty")
        assert asset.reputation_score == 0.0

    def test_optionality_score_with_high_deploy_time(self):
        """High time_to_deploy penalizes optionality score."""
        asset = StrategicAsset(
            title="Slow",
            portability_score=5,
            market_demand=5,
            monetization_potential=5,
            time_to_deploy=10,
        )
        # (5 + 5 + 5 + (10-10)) / 4 = 15/4 = 3.75
        assert asset.optionality_score == 3.75


class TestInfluenceDelta:
    """Tests for InfluenceDelta computed_delta."""

    def test_computed_delta_all_true(self):
        delta = InfluenceDelta(
            week_start="2026-03-02",
            advice_sought=True,
            decision_changed=True,
            framing_adopted=True,
            consultation_count=3,
        )
        # 2 + 3 + 3 + 3 = 11 → capped at 10
        assert delta.computed_delta == 10

    def test_computed_delta_none(self):
        delta = InfluenceDelta(week_start="2026-03-02")
        assert delta.computed_delta == 0

    def test_computed_delta_partial(self):
        delta = InfluenceDelta(
            week_start="2026-03-02",
            advice_sought=True,
            consultation_count=2,
        )
        # 2 + 2 = 4
        assert delta.computed_delta == 4

    def test_consultation_count_cap(self):
        """Consultation count contribution capped at 4."""
        delta = InfluenceDelta(
            week_start="2026-03-02",
            consultation_count=10,
        )
        assert delta.computed_delta == 4


class TestStakeholder:
    """Tests for Stakeholder model validation."""

    def test_valid_stakeholder(self):
        s = Stakeholder(
            name="Alice",
            role="VP Engineering",
            influence_level=8,
            alignment_score=3,
            dependency_on_you=6,
            trust_score=7,
        )
        assert s.name == "Alice"
        assert s.alignment_score == 3

    def test_default_stakeholder(self):
        s = Stakeholder(name="Bob")
        assert s.influence_level == 5
        assert s.alignment_score == 0
        assert s.trust_score == 5


# ── Repository Tests ─────────────────────────────────────────────

class TestStrategyRepository:
    """Tests for StrategyRepository CRUD operations."""

    @pytest.mark.asyncio
    async def test_save_and_get_stakeholder(self, strategy_repo):
        s = Stakeholder(name="Alice", role="VP Eng", influence_level=8)
        saved = await strategy_repo.save_stakeholder(s)
        assert saved.name == "Alice"

        fetched = await strategy_repo.get_stakeholder(saved.id)
        assert fetched is not None
        assert fetched.name == "Alice"
        assert fetched.influence_level == 8

    @pytest.mark.asyncio
    async def test_list_stakeholders(self, strategy_repo):
        await strategy_repo.save_stakeholder(Stakeholder(name="Low", influence_level=2))
        await strategy_repo.save_stakeholder(Stakeholder(name="High", influence_level=9))
        result = await strategy_repo.list_stakeholders()
        assert len(result) == 2
        assert result[0].name == "High"  # Ordered by influence DESC

    @pytest.mark.asyncio
    async def test_delete_stakeholder(self, strategy_repo):
        s = Stakeholder(name="Temp")
        await strategy_repo.save_stakeholder(s)
        deleted = await strategy_repo.delete_stakeholder(s.id)
        assert deleted is True
        assert await strategy_repo.get_stakeholder(s.id) is None

    @pytest.mark.asyncio
    async def test_save_and_get_initiative(self, strategy_repo):
        scores = InitiativeScores(authority=4, asymmetric_info=4, future_mobility=4,
                                  reusable_leverage=3, right_visibility=3)
        init = Initiative(
            title="Build AI Platform",
            scores=scores,
            category=scores.category,
            visibility=VisibilityLevel.EXECUTIVE,
        )
        saved = await strategy_repo.save_initiative(init)
        fetched = await strategy_repo.get_initiative(saved.id)
        assert fetched is not None
        assert fetched.title == "Build AI Platform"
        assert fetched.scores.total == 18
        assert fetched.category == InitiativeCategory.STRATEGIC

    @pytest.mark.asyncio
    async def test_list_initiatives_filter(self, strategy_repo):
        s1 = InitiativeScores(authority=5, asymmetric_info=5, future_mobility=4,
                              reusable_leverage=4, right_visibility=4)
        s2 = InitiativeScores(authority=1, asymmetric_info=1, future_mobility=1,
                              reusable_leverage=1, right_visibility=1)
        await strategy_repo.save_initiative(
            Initiative(title="Strategic", scores=s1, category=s1.category)
        )
        await strategy_repo.save_initiative(
            Initiative(title="Maintenance", scores=s2, category=s2.category)
        )
        strategic = await strategy_repo.list_initiatives(
            category=InitiativeCategory.STRATEGIC
        )
        assert len(strategic) == 1
        assert strategic[0].title == "Strategic"

    @pytest.mark.asyncio
    async def test_save_and_list_assets(self, strategy_repo):
        asset = StrategicAsset(
            title="Public AI Framework",
            asset_type=AssetCategory.REPUTATION,
            visibility=VisibilityLevel.MARKET,
            signaling_strength=8,
        )
        await strategy_repo.save_asset(asset)
        result = await strategy_repo.list_assets()
        assert len(result) == 1
        assert result[0].title == "Public AI Framework"
        assert result[0].signaling_strength == 8

    @pytest.mark.asyncio
    async def test_list_assets_filter(self, strategy_repo):
        await strategy_repo.save_asset(
            StrategicAsset(title="Rep", asset_type=AssetCategory.REPUTATION)
        )
        await strategy_repo.save_asset(
            StrategicAsset(title="Opt", asset_type=AssetCategory.OPTIONALITY)
        )
        rep = await strategy_repo.list_assets(asset_type=AssetCategory.REPUTATION)
        assert len(rep) == 1
        assert rep[0].title == "Rep"

    @pytest.mark.asyncio
    async def test_save_and_get_influence_delta(self, strategy_repo):
        delta = InfluenceDelta(
            week_start="2026-03-02",
            advice_sought=True,
            decision_changed=True,
            delta_score=5,
        )
        await strategy_repo.save_influence_delta(delta)
        fetched = await strategy_repo.get_influence_delta_for_week("2026-03-02")
        assert fetched is not None
        assert fetched.advice_sought is True
        assert fetched.delta_score == 5

    @pytest.mark.asyncio
    async def test_list_influence_deltas(self, strategy_repo):
        for i in range(5):
            await strategy_repo.save_influence_delta(
                InfluenceDelta(week_start=f"2026-0{i+1}-01", delta_score=i)
            )
        result = await strategy_repo.list_influence_deltas(limit=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_save_and_get_simulation(self, strategy_repo):
        sim = WeeklySimulation(
            week_start="2026-03-02",
            strategic_move="Ship AI framework MVP",
            maintenance_tasks=["Review backlog", "Update docs"],
            position_building=["Present at team demo"],
            influence_trend="up",
            optionality_trend="flat",
        )
        await strategy_repo.save_simulation(sim)
        latest = await strategy_repo.get_latest_simulation()
        assert latest is not None
        assert latest.strategic_move == "Ship AI framework MVP"
        assert len(latest.maintenance_tasks) == 2

    @pytest.mark.asyncio
    async def test_strategy_summary(self, strategy_repo):
        s1 = InitiativeScores(authority=5, asymmetric_info=5, future_mobility=4,
                              reusable_leverage=4, right_visibility=4)
        await strategy_repo.save_initiative(
            Initiative(title="I1", scores=s1, category=s1.category,
                       visibility=VisibilityLevel.EXECUTIVE)
        )
        await strategy_repo.save_stakeholder(Stakeholder(name="S1"))
        await strategy_repo.save_asset(
            StrategicAsset(title="A1", asset_type=AssetCategory.REPUTATION)
        )

        summary = await strategy_repo.get_strategy_summary()
        assert summary["stakeholder_count"] == 1
        assert "strategic" in summary["initiative_counts"]
        assert "reputation" in summary["asset_counts"]


# ── Evaluation Engine Tests ──────────────────────────────────────

class TestMoveEvaluationEngine:
    """Tests for the Move Evaluation Engine."""

    @pytest.mark.asyncio
    async def test_evaluate_strategic(self, evaluation_engine):
        create = InitiativeCreate(
            title="AI Platform",
            authority=5, asymmetric_info=4, future_mobility=4,
            reusable_leverage=3, right_visibility=3,
        )
        result = await evaluation_engine.evaluate_initiative(create)
        assert result.category == InitiativeCategory.STRATEGIC
        assert result.scores.total == 19

    @pytest.mark.asyncio
    async def test_evaluate_maintenance(self, evaluation_engine):
        create = InitiativeCreate(
            title="Fix typos",
            authority=1, asymmetric_info=0, future_mobility=0,
            reusable_leverage=1, right_visibility=0,
        )
        result = await evaluation_engine.evaluate_initiative(create)
        assert result.category == InitiativeCategory.MAINTENANCE
        assert result.scores.total == 2

    @pytest.mark.asyncio
    async def test_get_strategic_moves(self, evaluation_engine):
        await evaluation_engine.evaluate_initiative(
            InitiativeCreate(
                title="Strategic",
                authority=5, asymmetric_info=5, future_mobility=4,
                reusable_leverage=4, right_visibility=4,
            )
        )
        await evaluation_engine.evaluate_initiative(
            InitiativeCreate(title="Maint", authority=1),
        )
        strategic = await evaluation_engine.get_strategic_moves()
        assert len(strategic) == 1
        assert strategic[0].title == "Strategic"

    @pytest.mark.asyncio
    async def test_category_breakdown(self, evaluation_engine):
        await evaluation_engine.evaluate_initiative(
            InitiativeCreate(
                title="S1",
                authority=5, asymmetric_info=5, future_mobility=4,
                reusable_leverage=4, right_visibility=4,
            )
        )
        await evaluation_engine.evaluate_initiative(
            InitiativeCreate(
                title="Sup1",
                authority=3, asymmetric_info=3, future_mobility=2,
                reusable_leverage=2, right_visibility=2,
            )
        )
        breakdown = await evaluation_engine.get_category_breakdown()
        assert len(breakdown["strategic"]) == 1
        assert len(breakdown["supportive"]) == 1

    @pytest.mark.asyncio
    async def test_visibility_matrix(self, evaluation_engine):
        await evaluation_engine.evaluate_initiative(
            InitiativeCreate(
                title="Vis",
                authority=5, asymmetric_info=5, future_mobility=4,
                reusable_leverage=4, right_visibility=4,
                visibility=VisibilityLevel.MARKET,
            )
        )
        matrix = await evaluation_engine.get_visibility_matrix()
        assert matrix["market"] == 1
        assert matrix["hidden"] == 0

    def test_get_questions(self):
        questions = MoveEvaluationEngine.get_questions()
        assert len(questions) == 5
        assert questions[0]["key"] == "authority"


# ── Influence Tracker Tests ──────────────────────────────────────

class TestInfluenceTracker:
    """Tests for the InfluenceTracker."""

    @pytest.mark.asyncio
    async def test_log_week(self, influence_tracker):
        create = InfluenceDeltaCreate(
            week_start="2026-03-02",
            advice_sought=True,
            decision_changed=True,
            consultation_count=2,
        )
        result = await influence_tracker.log_week(create)
        assert result.delta_score == result.computed_delta
        assert result.delta_score > 0

    @pytest.mark.asyncio
    async def test_get_trend_empty(self, influence_tracker):
        trend = await influence_tracker.get_trend()
        assert trend["direction"] == "flat"
        assert trend["average"] == 0.0

    @pytest.mark.asyncio
    async def test_get_trend_with_data(self, influence_tracker):
        for i in range(6):
            await influence_tracker.log_week(
                InfluenceDeltaCreate(
                    week_start=f"2026-0{i+1}-01",
                    consultation_count=i + 1,
                )
            )
        trend = await influence_tracker.get_trend()
        assert trend["direction"] in ("up", "down", "flat")
        assert len(trend["recent_scores"]) == 6

    @pytest.mark.asyncio
    async def test_log_week_with_stakeholder(self, influence_tracker, strategy_repo):
        """Log week with stakeholder_id resolves name."""
        sh = Stakeholder(name="Alice", role="VP Eng", influence_level=8)
        await strategy_repo.save_stakeholder(sh)

        create = InfluenceDeltaCreate(
            week_start="2026-04-01",
            advice_sought=True,
            consultation_count=1,
            stakeholder_id=str(sh.id),
        )
        result = await influence_tracker.log_week(create)
        assert result.stakeholder_name == "Alice"
        assert result.stakeholder_id == str(sh.id)

    @pytest.mark.asyncio
    async def test_log_week_invalid_stakeholder(self, influence_tracker):
        """Log week with invalid stakeholder_id ignores it gracefully."""
        create = InfluenceDeltaCreate(
            week_start="2026-04-01",
            advice_sought=True,
            stakeholder_id="00000000-0000-0000-0000-000000000000",
        )
        result = await influence_tracker.log_week(create)
        assert result.stakeholder_name is None

    @pytest.mark.asyncio
    async def test_get_insights_empty(self, influence_tracker):
        """Insights on empty data returns safe defaults."""
        insights = await influence_tracker.get_insights()
        assert insights["trend"]["direction"] == "flat"
        assert insights["streaks"]["current"] == 0
        assert insights["streaks"]["best"] == 0
        assert insights["signal_breakdown"]["advice_sought"] == 0
        assert insights["signal_breakdown"]["decision_changed"] == 0
        assert insights["stakeholder_heatmap"] == []
        assert len(insights["recommendations"]) >= 1  # Has starter recommendation

    @pytest.mark.asyncio
    async def test_get_insights_with_data(self, influence_tracker):
        """Insights compute correctly with several weeks of data."""
        # Log 6 weeks with increasing engagement
        for i in range(6):
            await influence_tracker.log_week(
                InfluenceDeltaCreate(
                    week_start=f"2026-0{i + 1}-01",
                    advice_sought=True,
                    decision_changed=(i >= 3),
                    framing_adopted=(i >= 4),
                    consultation_count=i + 1,
                )
            )

        insights = await influence_tracker.get_insights(weeks=6)

        # Should have trend data
        assert insights["trend"]["direction"] in ("up", "down", "flat")
        assert len(insights["trend"]["recent_scores"]) > 0

        # Signal breakdown should have advice_sought
        assert "advice_sought" in insights["signal_breakdown"]
        assert insights["signal_breakdown"]["advice_sought"] == 6

        # Peak/valley present
        assert insights["peak_week"] is not None
        assert insights["valley_week"] is not None
        assert insights["peak_week"]["score"] >= insights["valley_week"]["score"]

    @pytest.mark.asyncio
    async def test_get_insights_stakeholder_heatmap(
        self, influence_tracker, strategy_repo
    ):
        """Stakeholder heatmap tracks attributed influence."""
        sh = Stakeholder(name="Bob", role="CTO", influence_level=9)
        await strategy_repo.save_stakeholder(sh)

        # 3 weeks attributed to Bob
        for i in range(3):
            await influence_tracker.log_week(
                InfluenceDeltaCreate(
                    week_start=f"2026-0{i + 1}-10",
                    advice_sought=True,
                    consultation_count=2,
                    stakeholder_id=str(sh.id),
                )
            )
        # 1 week unattributed
        await influence_tracker.log_week(
            InfluenceDeltaCreate(
                week_start="2026-04-10",
                consultation_count=1,
            )
        )

        insights = await influence_tracker.get_insights(weeks=12)
        heatmap = insights["stakeholder_heatmap"]

        assert len(heatmap) >= 1
        bob_entry = next((h for h in heatmap if h["name"] == "Bob"), None)
        assert bob_entry is not None
        assert bob_entry["weeks"] == 3
        assert bob_entry["total_score"] > 0

    @pytest.mark.asyncio
    async def test_get_insights_streaks(self, influence_tracker):
        """Streak detection works for consecutive high-score weeks."""
        # Log 5 high-scoring weeks (score >= 5 each)
        for i in range(5):
            await influence_tracker.log_week(
                InfluenceDeltaCreate(
                    week_start=f"2026-01-{(i + 1) * 7:02d}",
                    advice_sought=True,
                    decision_changed=True,
                    consultation_count=2,
                )
            )

        insights = await influence_tracker.get_insights(weeks=12)
        assert insights["streaks"]["best"] >= 3  # at least 3 consecutive high weeks

    @pytest.mark.asyncio
    async def test_get_insights_recommendations(self, influence_tracker):
        """Recommendations generated when engagement patterns detected."""
        # Log several weeks with advice but no framing adopted
        for i in range(4):
            await influence_tracker.log_week(
                InfluenceDeltaCreate(
                    week_start=f"2026-0{i + 1}-01",
                    advice_sought=True,
                    decision_changed=False,
                    framing_adopted=False,
                    consultation_count=1,
                )
            )

        insights = await influence_tracker.get_insights(weeks=12)
        # Should have at least one recommendation about framing or decisions
        assert len(insights["recommendations"]) > 0


class TestInfluenceDeltaStakeholderFields:
    """Tests for stakeholder fields on InfluenceDelta model."""

    def test_defaults_to_none(self):
        delta = InfluenceDelta(week_start="2026-03-02")
        assert delta.stakeholder_id is None
        assert delta.stakeholder_name is None

    def test_stakeholder_fields_set(self):
        delta = InfluenceDelta(
            week_start="2026-03-02",
            stakeholder_id="abc-123",
            stakeholder_name="Alice",
            advice_sought=True,
        )
        assert delta.stakeholder_id == "abc-123"
        assert delta.stakeholder_name == "Alice"
        assert delta.computed_delta == 2

    def test_create_with_stakeholder_id(self):
        create = InfluenceDeltaCreate(
            week_start="2026-03-02",
            stakeholder_id="def-456",
        )
        assert create.stakeholder_id == "def-456"


class TestInfluenceRepository:
    """Tests for stakeholder persistence on influence deltas."""

    @pytest.mark.asyncio
    async def test_save_and_retrieve_with_stakeholder(self, strategy_repo):
        """Stakeholder fields round-trip through the database."""
        delta = InfluenceDelta(
            week_start="2026-04-01",
            advice_sought=True,
            consultation_count=2,
            stakeholder_id="test-id-123",
            stakeholder_name="Test Person",
            delta_score=4,
        )
        await strategy_repo.save_influence_delta(delta)

        deltas = await strategy_repo.list_influence_deltas(limit=5)
        assert len(deltas) == 1
        assert deltas[0].stakeholder_id == "test-id-123"
        assert deltas[0].stakeholder_name == "Test Person"

    @pytest.mark.asyncio
    async def test_save_without_stakeholder(self, strategy_repo):
        """Deltas without stakeholder still work."""
        delta = InfluenceDelta(
            week_start="2026-04-01",
            advice_sought=True,
            delta_score=2,
        )
        await strategy_repo.save_influence_delta(delta)

        deltas = await strategy_repo.list_influence_deltas(limit=5)
        assert len(deltas) == 1
        assert deltas[0].stakeholder_id is None
        assert deltas[0].stakeholder_name is None


# ── Simulation Tests ─────────────────────────────────────────────

class TestStrategicSimulator:
    """Tests for the StrategicSimulator."""

    @pytest.mark.asyncio
    async def test_run_simulation_no_data(self, simulator):
        """Simulation works with no data (rule-based fallback)."""
        result = await simulator.run_simulation("2026-03-02")
        assert result.week_start == "2026-03-02"
        assert result.strategic_move != ""
        assert isinstance(result.maintenance_tasks, list)

    @pytest.mark.asyncio
    async def test_run_simulation_with_initiatives(self, simulator, strategy_repo):
        scores = InitiativeScores(authority=5, asymmetric_info=5, future_mobility=4,
                                  reusable_leverage=4, right_visibility=4)
        await strategy_repo.save_initiative(
            Initiative(title="AI Platform", scores=scores, category=scores.category)
        )
        result = await simulator.run_simulation("2026-03-02")
        assert "AI Platform" in result.strategic_move

    @pytest.mark.asyncio
    async def test_parse_llm_output(self, simulator):
        raw = (
            "STRATEGIC_MOVE: Ship the AI framework MVP\n"
            "MAINTENANCE: Update docs | Fix CI pipeline\n"
            "POSITION_BUILDING: Present at all-hands | Tweet about framework\n"
            "INFLUENCE_TREND: up - more consultations\n"
            "OPTIONALITY_TREND: flat - no new portable assets\n"
            "TOP_INITIATIVES: AI Framework | Second Brain\n"
        )
        sim = simulator._parse_llm_output("2026-03-02", raw)
        assert sim.strategic_move == "Ship the AI framework MVP"
        assert len(sim.maintenance_tasks) == 2
        assert len(sim.position_building) == 2
        assert "up" in sim.influence_trend
        assert len(sim.top_initiatives) == 2

    @pytest.mark.asyncio
    async def test_rule_based_simulation(self, simulator):
        scores = InitiativeScores(authority=5, asymmetric_info=5, future_mobility=4,
                                  reusable_leverage=4, right_visibility=4)
        initiatives = [
            Initiative(title="Big Move", scores=scores, category=scores.category),
        ]
        sim = simulator._rule_based_simulation(
            "2026-03-02", initiatives, {"direction": "up", "average": 5.0}
        )
        assert "Big Move" in sim.strategic_move
        assert sim.influence_trend == "up"


# ── Mandatory Initiative Tests ────────────────────────────────────

class TestMandatoryInitiatives:
    """Tests for mandatory initiative type."""

    def test_initiative_type_default(self):
        init = Initiative(title="Test")
        assert init.initiative_type == InitiativeType.SCORED

    def test_initiative_type_mandatory(self):
        init = Initiative(title="Test", initiative_type=InitiativeType.MANDATORY)
        assert init.initiative_type == InitiativeType.MANDATORY

    def test_mandatory_create(self):
        create = InitiativeCreate(
            title="Must Do",
            initiative_type=InitiativeType.MANDATORY,
        )
        assert create.initiative_type == InitiativeType.MANDATORY
        assert create.authority == 0  # Not scored

    @pytest.mark.asyncio
    async def test_evaluate_mandatory_no_scores(self, evaluation_engine):
        """Mandatory initiative with no scores defaults to maintenance."""
        create = InitiativeCreate(
            title="Compliance Audit",
            initiative_type=InitiativeType.MANDATORY,
        )
        result = await evaluation_engine.evaluate_initiative(create)
        assert result.initiative_type == InitiativeType.MANDATORY
        assert result.category == InitiativeCategory.MAINTENANCE
        assert result.scores.total == 0

    @pytest.mark.asyncio
    async def test_evaluate_mandatory_with_scores(self, evaluation_engine):
        """Mandatory initiative with scores still computes category."""
        create = InitiativeCreate(
            title="Ship API",
            initiative_type=InitiativeType.MANDATORY,
            authority=5, asymmetric_info=4, future_mobility=4,
            reusable_leverage=3, right_visibility=3,
        )
        result = await evaluation_engine.evaluate_initiative(create)
        assert result.initiative_type == InitiativeType.MANDATORY
        assert result.category == InitiativeCategory.STRATEGIC  # Score 19

    @pytest.mark.asyncio
    async def test_save_and_retrieve_mandatory(self, strategy_repo):
        """Mandatory type persists through save/load."""
        init = Initiative(
            title="Annual Report",
            initiative_type=InitiativeType.MANDATORY,
        )
        saved = await strategy_repo.save_initiative(init)
        fetched = await strategy_repo.get_initiative(saved.id)
        assert fetched is not None
        assert fetched.initiative_type == InitiativeType.MANDATORY

    @pytest.mark.asyncio
    async def test_list_filter_by_type(self, strategy_repo):
        """Can filter initiatives by type."""
        await strategy_repo.save_initiative(
            Initiative(title="Scored One", initiative_type=InitiativeType.SCORED)
        )
        await strategy_repo.save_initiative(
            Initiative(title="Must Do", initiative_type=InitiativeType.MANDATORY)
        )
        mandatory = await strategy_repo.list_initiatives(
            initiative_type=InitiativeType.MANDATORY
        )
        assert len(mandatory) == 1
        assert mandatory[0].title == "Must Do"


# ── Initiative Link Tests ───────────────────────────────────────

class TestInitiativeLinks:
    """Tests for initiative link CRUD."""

    @pytest.mark.asyncio
    async def test_save_and_get_links(self, strategy_repo):
        init = Initiative(title="Linked Init")
        await strategy_repo.save_initiative(init)

        link = InitiativeLink(
            initiative_id=init.id,
            linked_type="entry",
            linked_id=str(uuid4()),
            linked_title="Some Brain Entry",
            link_note="Related project",
        )
        await strategy_repo.save_initiative_link(link)

        links = await strategy_repo.get_links_for_initiative(init.id)
        assert len(links) == 1
        assert links[0].linked_title == "Some Brain Entry"
        assert links[0].link_note == "Related project"
        assert links[0].linked_type == "entry"

    @pytest.mark.asyncio
    async def test_multiple_links(self, strategy_repo):
        init = Initiative(title="Multi-link")
        await strategy_repo.save_initiative(init)

        entry_id = str(uuid4())
        entity_id = str(uuid4())
        await strategy_repo.save_initiative_link(
            InitiativeLink(
                initiative_id=init.id,
                linked_type="entry",
                linked_id=entry_id,
                linked_title="Entry A",
            )
        )
        await strategy_repo.save_initiative_link(
            InitiativeLink(
                initiative_id=init.id,
                linked_type="entity",
                linked_id=entity_id,
                linked_title="Project Phoenix",
            )
        )

        links = await strategy_repo.get_links_for_initiative(init.id)
        assert len(links) == 2
        types = {l.linked_type for l in links}
        assert types == {"entry", "entity"}

    @pytest.mark.asyncio
    async def test_delete_link(self, strategy_repo):
        init = Initiative(title="Del Link")
        await strategy_repo.save_initiative(init)

        link = InitiativeLink(
            initiative_id=init.id,
            linked_type="entry",
            linked_id=str(uuid4()),
            linked_title="To Remove",
        )
        await strategy_repo.save_initiative_link(link)
        assert await strategy_repo.count_links_for_initiative(init.id) == 1

        deleted = await strategy_repo.delete_initiative_link(link.id)
        assert deleted is True
        assert await strategy_repo.count_links_for_initiative(init.id) == 0

    @pytest.mark.asyncio
    async def test_count_links(self, strategy_repo):
        init = Initiative(title="Count")
        await strategy_repo.save_initiative(init)
        assert await strategy_repo.count_links_for_initiative(init.id) == 0

        for i in range(3):
            await strategy_repo.save_initiative_link(
                InitiativeLink(
                    initiative_id=init.id,
                    linked_type="entry",
                    linked_id=str(uuid4()),
                    linked_title=f"Entry {i}",
                )
            )
        assert await strategy_repo.count_links_for_initiative(init.id) == 3

    @pytest.mark.asyncio
    async def test_get_initiatives_for_linked_item(self, strategy_repo):
        """Find all initiatives linked to a specific entry/entity."""
        init1 = Initiative(title="Init 1")
        init2 = Initiative(title="Init 2")
        await strategy_repo.save_initiative(init1)
        await strategy_repo.save_initiative(init2)

        shared_id = str(uuid4())
        await strategy_repo.save_initiative_link(
            InitiativeLink(
                initiative_id=init1.id,
                linked_type="entity",
                linked_id=shared_id,
                linked_title="Shared Entity",
            )
        )
        await strategy_repo.save_initiative_link(
            InitiativeLink(
                initiative_id=init2.id,
                linked_type="entity",
                linked_id=shared_id,
                linked_title="Shared Entity",
            )
        )

        links = await strategy_repo.get_initiatives_for_linked_item(shared_id)
        assert len(links) == 2
        initiative_ids = {str(l.initiative_id) for l in links}
        assert str(init1.id) in initiative_ids
        assert str(init2.id) in initiative_ids


# ── Initiative Fuzzy Match & Auto-Link Tests ─────────────────────


class TestInitiativeFuzzyMatch:
    """Tests for find_initiatives_by_title and link_exists."""

    @pytest.mark.asyncio
    async def test_exact_match(self, strategy_repo):
        """Exact title match returns the initiative."""
        init = Initiative(title="Platform Rewrite")
        await strategy_repo.save_initiative(init)

        matches = await strategy_repo.find_initiatives_by_title("Platform Rewrite")
        assert len(matches) == 1
        assert matches[0].title == "Platform Rewrite"

    @pytest.mark.asyncio
    async def test_case_insensitive_match(self, strategy_repo):
        """Match is case-insensitive."""
        init = Initiative(title="Platform Rewrite")
        await strategy_repo.save_initiative(init)

        matches = await strategy_repo.find_initiatives_by_title("platform rewrite")
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_query_inside_title(self, strategy_repo):
        """Query that's a substring of the initiative title matches."""
        init = Initiative(title="Platform Rewrite Phase 2")
        await strategy_repo.save_initiative(init)

        matches = await strategy_repo.find_initiatives_by_title("Platform Rewrite")
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_title_inside_query(self, strategy_repo):
        """Initiative title that's a substring of the query matches."""
        init = Initiative(title="Platform Rewrite")
        await strategy_repo.save_initiative(init)

        matches = await strategy_repo.find_initiatives_by_title(
            "Platform Rewrite Phase 2 Kickoff"
        )
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_no_match(self, strategy_repo):
        """Non-matching title returns empty."""
        init = Initiative(title="Platform Rewrite")
        await strategy_repo.save_initiative(init)

        matches = await strategy_repo.find_initiatives_by_title("Auth Migration")
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_only_active_by_default(self, strategy_repo):
        """Only active initiatives are returned by default."""
        active = Initiative(title="Platform Rewrite", status="active")
        paused = Initiative(title="Platform Rewrite Legacy", status="paused")
        await strategy_repo.save_initiative(active)
        await strategy_repo.save_initiative(paused)

        matches = await strategy_repo.find_initiatives_by_title("Platform Rewrite")
        assert len(matches) == 1
        assert matches[0].status == "active"

    @pytest.mark.asyncio
    async def test_all_statuses(self, strategy_repo):
        """Pass status=None to match all statuses."""
        active = Initiative(title="Platform Rewrite", status="active")
        paused = Initiative(title="Platform Rewrite Legacy", status="paused")
        await strategy_repo.save_initiative(active)
        await strategy_repo.save_initiative(paused)

        matches = await strategy_repo.find_initiatives_by_title(
            "Platform Rewrite", status=None
        )
        assert len(matches) == 2

    @pytest.mark.asyncio
    async def test_exact_match_ranked_first(self, strategy_repo):
        """Exact match is ranked above substring matches."""
        contains = Initiative(title="Platform Rewrite Phase 2")
        exact = Initiative(title="Platform Rewrite")
        await strategy_repo.save_initiative(contains)
        await strategy_repo.save_initiative(exact)

        matches = await strategy_repo.find_initiatives_by_title("Platform Rewrite")
        assert len(matches) == 2
        assert matches[0].title == "Platform Rewrite"  # exact first

    @pytest.mark.asyncio
    async def test_link_exists_true(self, strategy_repo):
        """link_exists returns True when link is present."""
        init = Initiative(title="Test")
        await strategy_repo.save_initiative(init)
        entry_id = str(uuid4())
        await strategy_repo.save_initiative_link(
            InitiativeLink(
                initiative_id=init.id,
                linked_type="entry",
                linked_id=entry_id,
                linked_title="Test Entry",
            )
        )

        assert await strategy_repo.link_exists(init.id, entry_id) is True

    @pytest.mark.asyncio
    async def test_link_exists_false(self, strategy_repo):
        """link_exists returns False when no link exists."""
        init = Initiative(title="Test")
        await strategy_repo.save_initiative(init)

        assert await strategy_repo.link_exists(init.id, str(uuid4())) is False


# ── Pipeline Auto-Link Tests ────────────────────────────────────


class TestPipelineAutoLink:
    """Tests for CapturePipeline._auto_link_initiatives."""

    @pytest.fixture
    async def strategy_db(self) -> AsyncGenerator[Database, None]:
        database = Database(":memory:")
        await database.init_db()
        yield database

    @pytest.fixture
    async def strategy_repo(self, strategy_db: Database) -> StrategyRepository:
        return StrategyRepository(strategy_db)

    @pytest.fixture
    def pipeline_with_strategy(
        self, mock_classifier, mock_vector_store, mock_collector,
        strategy_db, strategy_repo,
    ):
        """Pipeline with mocked deps + real strategy repo (shared DB)."""
        from src.storage.repository import BrainEntryRepository
        from src.core.pipeline import CapturePipeline
        repo = BrainEntryRepository(strategy_db)
        return CapturePipeline(
            classifier=mock_classifier,
            repository=repo,
            vector_store=mock_vector_store,
            collector=mock_collector,
            strategy_repo=strategy_repo,
        )

    @pytest.mark.asyncio
    async def test_auto_links_entry_to_matching_initiative(
        self, pipeline_with_strategy, strategy_repo,
    ):
        """Entry with project field matching an initiative gets auto-linked."""
        from src.models.brain_entry import BrainEntry
        from src.models.enums import EntryType

        init = Initiative(title="Platform Rewrite")
        await strategy_repo.save_initiative(init)

        entry = BrainEntry(
            type=EntryType.IDEA,
            title="OAuth2 Migration",
            summary="Migrate auth to OAuth2",
            raw_content="Migrate auth for platform rewrite",
            project="Platform Rewrite",
            author_id="U1",
            author_name="Michelle",
        )

        links = await pipeline_with_strategy._auto_link_initiatives(entry)
        assert len(links) == 1
        assert str(links[0].initiative_id) == str(init.id)
        assert links[0].linked_id == str(entry.id)
        assert "Platform Rewrite" in links[0].link_note

    @pytest.mark.asyncio
    async def test_auto_links_via_extracted_entities(
        self, pipeline_with_strategy, strategy_repo,
    ):
        """Entry with extracted entity matching an initiative gets linked."""
        from src.models.brain_entry import BrainEntry
        from src.models.enums import EntryType

        init = Initiative(title="Auth Service")
        await strategy_repo.save_initiative(init)

        entry = BrainEntry(
            type=EntryType.NOTE,
            title="Auth Notes",
            summary="Notes about auth",
            raw_content="Notes about auth service",
            extracted_entities=["Auth Service", "OAuth2"],
            author_id="U1",
            author_name="Michelle",
        )

        links = await pipeline_with_strategy._auto_link_initiatives(entry)
        assert len(links) == 1
        assert str(links[0].initiative_id) == str(init.id)

    @pytest.mark.asyncio
    async def test_no_duplicate_links(
        self, pipeline_with_strategy, strategy_repo,
    ):
        """Running auto-link twice doesn't create duplicate links."""
        from src.models.brain_entry import BrainEntry
        from src.models.enums import EntryType

        init = Initiative(title="Platform Rewrite")
        await strategy_repo.save_initiative(init)

        entry = BrainEntry(
            type=EntryType.IDEA,
            title="Test",
            summary="Test",
            raw_content="Test",
            project="Platform Rewrite",
            author_id="U1",
            author_name="Michelle",
        )

        links1 = await pipeline_with_strategy._auto_link_initiatives(entry)
        links2 = await pipeline_with_strategy._auto_link_initiatives(entry)
        assert len(links1) == 1
        assert len(links2) == 0  # No duplicate

    @pytest.mark.asyncio
    async def test_no_strategy_repo_returns_empty(
        self, mock_classifier, mock_vector_store, mock_collector, db,
    ):
        """Pipeline without strategy_repo returns empty list."""
        from src.core.pipeline import CapturePipeline
        from src.storage.repository import BrainEntryRepository
        from src.models.brain_entry import BrainEntry
        from src.models.enums import EntryType

        pipeline = CapturePipeline(
            classifier=mock_classifier,
            repository=BrainEntryRepository(db),
            vector_store=mock_vector_store,
            collector=mock_collector,
        )

        entry = BrainEntry(
            type=EntryType.IDEA,
            title="Test",
            summary="Test",
            raw_content="Test",
            project="Some Project",
            author_id="U1",
            author_name="Michelle",
        )

        links = await pipeline._auto_link_initiatives(entry)
        assert links == []

    @pytest.mark.asyncio
    async def test_no_match_returns_empty(
        self, pipeline_with_strategy, strategy_repo,
    ):
        """Entry whose project doesn't match any initiative gets no links."""
        from src.models.brain_entry import BrainEntry
        from src.models.enums import EntryType

        init = Initiative(title="Platform Rewrite")
        await strategy_repo.save_initiative(init)

        entry = BrainEntry(
            type=EntryType.IDEA,
            title="Test",
            summary="Test",
            raw_content="Test",
            project="Totally Unrelated",
            author_id="U1",
            author_name="Michelle",
        )

        links = await pipeline_with_strategy._auto_link_initiatives(entry)
        assert links == []


# ── Example Dataset Tests ────────────────────────────────────────


class TestExampleDatasets:
    """Tests for enhanced example datasets with stakeholder attribution."""

    def test_corporate_influence_has_stakeholder_names(self):
        from src.core.example_datasets import CORPORATE_INFLUENCE
        attributed = [d for d in CORPORATE_INFLUENCE if d.stakeholder_name]
        assert len(attributed) >= 8, "Most corporate influence entries should have stakeholder attribution"

    def test_personal_influence_has_stakeholder_names(self):
        from src.core.example_datasets import PERSONAL_INFLUENCE
        attributed = [d for d in PERSONAL_INFLUENCE if d.stakeholder_name]
        assert len(attributed) >= 7, "Most personal influence entries should have stakeholder attribution"

    def test_corporate_influence_has_varied_scores(self):
        from src.core.example_datasets import CORPORATE_INFLUENCE
        scores = [d.computed_delta for d in CORPORATE_INFLUENCE]
        assert min(scores) < 3, "Should include low-score weeks"
        assert max(scores) >= 8, "Should include high-score weeks"
        assert len(scores) >= 10, "Should have at least 10 weeks of data"

    def test_personal_influence_has_varied_scores(self):
        from src.core.example_datasets import PERSONAL_INFLUENCE
        scores = [d.computed_delta for d in PERSONAL_INFLUENCE]
        assert min(scores) == 0, "Should include zero-score weeks"
        assert max(scores) >= 8, "Should include high-score weeks"
        assert len(scores) >= 10, "Should have at least 10 weeks of data"

    def test_corporate_stakeholder_names_match_stakeholders(self):
        from src.core.example_datasets import CORPORATE_INFLUENCE, CORPORATE_STAKEHOLDERS
        stakeholder_names = {s.name for s in CORPORATE_STAKEHOLDERS}
        for delta in CORPORATE_INFLUENCE:
            if delta.stakeholder_name:
                assert delta.stakeholder_name in stakeholder_names, (
                    f"'{delta.stakeholder_name}' not in corporate stakeholders"
                )

    def test_personal_stakeholder_names_match_stakeholders(self):
        from src.core.example_datasets import PERSONAL_INFLUENCE, PERSONAL_STAKEHOLDERS
        stakeholder_names = {s.name for s in PERSONAL_STAKEHOLDERS}
        for delta in PERSONAL_INFLUENCE:
            if delta.stakeholder_name:
                assert delta.stakeholder_name in stakeholder_names, (
                    f"'{delta.stakeholder_name}' not in personal stakeholders"
                )

    @pytest.mark.asyncio
    async def test_load_corporate_dataset(self, strategy_repo):
        from src.core.example_datasets import load_example_dataset
        counts = await load_example_dataset(strategy_repo, "corporate")
        assert counts["stakeholders"] == 5
        assert counts["initiatives"] >= 5
        assert counts["assets"] >= 5
        assert counts["influence_deltas"] == 10

    @pytest.mark.asyncio
    async def test_load_personal_dataset(self, strategy_repo):
        from src.core.example_datasets import load_example_dataset
        counts = await load_example_dataset(strategy_repo, "personal")
        assert counts["stakeholders"] == 5
        assert counts["initiatives"] >= 5
        assert counts["assets"] >= 5
        assert counts["influence_deltas"] == 10
