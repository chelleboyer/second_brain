"""Weekly Strategic Simulation — generates strategic moves from current state."""

from datetime import datetime, timezone

import structlog

from src.classification.provider import HuggingFaceProvider
from src.models.strategy import (
    InfluenceDelta,
    InfluenceDeltaCreate,
    WeeklySimulation,
)
from src.storage.strategy_repository import StrategyRepository

log = structlog.get_logger(__name__)


# ── Influence Tracker ────────────────────────────────────────────


class InfluenceTracker:
    """Tracks and computes weekly influence deltas."""

    def __init__(self, strategy_repo: StrategyRepository) -> None:
        self.strategy_repo = strategy_repo

    async def log_week(
        self, create: InfluenceDeltaCreate
    ) -> InfluenceDelta:
        """Log influence interactions for a week and compute delta."""
        delta = InfluenceDelta(
            week_start=create.week_start,
            advice_sought=create.advice_sought,
            decision_changed=create.decision_changed,
            framing_adopted=create.framing_adopted,
            consultation_count=create.consultation_count,
            notes=create.notes,
        )
        # Auto-compute delta score from interactions
        delta.delta_score = delta.computed_delta

        saved = await self.strategy_repo.save_influence_delta(delta)
        log.info(
            "influence_logged",
            week=saved.week_start,
            delta=saved.delta_score,
        )
        return saved

    async def get_trend(self, weeks: int = 8) -> dict:
        """Compute influence trend over N weeks.

        Returns:
            direction: 'up', 'down', or 'flat'
            recent_scores: list of delta scores
            average: mean delta score
        """
        deltas = await self.strategy_repo.list_influence_deltas(limit=weeks)
        if not deltas:
            return {"direction": "flat", "recent_scores": [], "average": 0.0}

        scores = [d.delta_score for d in deltas]
        avg = sum(scores) / len(scores)

        # Trend: compare recent half vs older half
        if len(scores) >= 4:
            recent = sum(scores[: len(scores) // 2]) / (len(scores) // 2)
            older = sum(scores[len(scores) // 2 :]) / (len(scores) - len(scores) // 2)
            if recent > older + 1:
                direction = "up"
            elif recent < older - 1:
                direction = "down"
            else:
                direction = "flat"
        else:
            direction = "flat" if avg < 3 else "up"

        return {
            "direction": direction,
            "recent_scores": scores,
            "average": round(avg, 2),
        }


# ── Weekly Simulation ────────────────────────────────────────────

SIMULATION_PROMPT = """You are a strategic advisor. Analyze the following strategic state and produce a weekly simulation output.

## Current Initiatives (Active)
{initiatives}

## Stakeholder Landscape
{stakeholders}

## Recent Influence Trend
{influence_trend}

## Strategic Assets
{assets}

---

Based on this state, provide:

1. **Strategic Move**: ONE highest-leverage action for this week. Be specific.
2. **Maintenance Tasks**: 2-3 keep-the-lights-on tasks that must happen.
3. **Position-Building**: 1-2 moves that compound your reputation or optionality.
4. **Influence Trend Assessment**: Is influence growing, declining, or flat? Why?
5. **Optionality Trend Assessment**: Are you more or less portable this week? Why?

Format your response EXACTLY as:
STRATEGIC_MOVE: <one clear action>
MAINTENANCE: <task1> | <task2> | <task3>
POSITION_BUILDING: <move1> | <move2>
INFLUENCE_TREND: <up|down|flat> - <reason>
OPTIONALITY_TREND: <up|down|flat> - <reason>
TOP_INITIATIVES: <initiative1> | <initiative2> | <initiative3>
"""


class StrategicSimulator:
    """Runs weekly strategic simulations using LLM analysis."""

    def __init__(
        self,
        strategy_repo: StrategyRepository,
        influence_tracker: InfluenceTracker,
        provider: HuggingFaceProvider | None = None,
    ) -> None:
        self.strategy_repo = strategy_repo
        self.influence_tracker = influence_tracker
        self.provider = provider

    async def run_simulation(self, week_start: str) -> WeeklySimulation:
        """Execute the weekly strategic simulation protocol.

        Gathers current state, runs LLM analysis (if available),
        and produces a structured WeeklySimulation.
        """
        log.info("simulation_starting", week=week_start)

        # Gather state
        initiatives = await self.strategy_repo.list_initiatives(status="active")
        stakeholders = await self.strategy_repo.list_stakeholders()
        assets = await self.strategy_repo.list_assets()
        influence_trend = await self.influence_tracker.get_trend()

        # Format for LLM
        init_text = self._format_initiatives(initiatives)
        stake_text = self._format_stakeholders(stakeholders)
        asset_text = self._format_assets(assets)
        trend_text = (
            f"Direction: {influence_trend['direction']}, "
            f"Avg score: {influence_trend['average']}, "
            f"Recent: {influence_trend['recent_scores']}"
        )

        # Try LLM analysis
        raw_analysis = ""
        if self.provider is not None:
            try:
                prompt = SIMULATION_PROMPT.format(
                    initiatives=init_text or "No active initiatives.",
                    stakeholders=stake_text or "No stakeholders tracked.",
                    influence_trend=trend_text,
                    assets=asset_text or "No assets tracked.",
                )
                raw_analysis = await self.provider.generate_text(prompt)
                log.info("simulation_llm_complete", length=len(raw_analysis))
            except Exception as e:
                log.warning("simulation_llm_failed", error=str(e))
                raw_analysis = ""

        # Parse or build simulation
        sim = self._parse_simulation(week_start, raw_analysis, initiatives, influence_trend)
        saved = await self.strategy_repo.save_simulation(sim)
        log.info("simulation_complete", week=week_start, move=sim.strategic_move)
        return saved

    def _parse_simulation(
        self,
        week_start: str,
        raw_analysis: str,
        initiatives: list,
        influence_trend: dict,
    ) -> WeeklySimulation:
        """Parse LLM output into a structured simulation, with fallback."""
        if raw_analysis:
            return self._parse_llm_output(week_start, raw_analysis)

        # Fallback: rule-based simulation
        return self._rule_based_simulation(week_start, initiatives, influence_trend)

    def _parse_llm_output(
        self, week_start: str, raw: str
    ) -> WeeklySimulation:
        """Parse structured LLM response."""
        strategic_move = ""
        maintenance: list[str] = []
        position_building: list[str] = []
        influence_trend = ""
        optionality_trend = ""
        top_initiatives: list[str] = []

        for line in raw.strip().split("\n"):
            line = line.strip()
            if line.startswith("STRATEGIC_MOVE:"):
                strategic_move = line.split(":", 1)[1].strip()
            elif line.startswith("MAINTENANCE:"):
                maintenance = [
                    t.strip() for t in line.split(":", 1)[1].split("|") if t.strip()
                ]
            elif line.startswith("POSITION_BUILDING:"):
                position_building = [
                    t.strip() for t in line.split(":", 1)[1].split("|") if t.strip()
                ]
            elif line.startswith("INFLUENCE_TREND:"):
                influence_trend = line.split(":", 1)[1].strip()
            elif line.startswith("OPTIONALITY_TREND:"):
                optionality_trend = line.split(":", 1)[1].strip()
            elif line.startswith("TOP_INITIATIVES:"):
                top_initiatives = [
                    t.strip() for t in line.split(":", 1)[1].split("|") if t.strip()
                ]

        return WeeklySimulation(
            week_start=week_start,
            strategic_move=strategic_move or "Review and re-score active initiatives.",
            maintenance_tasks=maintenance,
            position_building=position_building,
            influence_trend=influence_trend.split("-")[0].strip() if influence_trend else "flat",
            optionality_trend=optionality_trend.split("-")[0].strip() if optionality_trend else "flat",
            top_initiatives=top_initiatives,
            raw_analysis=raw,
        )

    @staticmethod
    def _rule_based_simulation(
        week_start: str,
        initiatives: list,
        influence_trend: dict,
    ) -> WeeklySimulation:
        """Generate a simulation without LLM — pure rules."""
        # Find top strategic initiative
        strategic = [i for i in initiatives if i.category.value == "strategic"]
        supportive = [i for i in initiatives if i.category.value == "supportive"]
        maintenance_inits = [i for i in initiatives if i.category.value == "maintenance"]

        if strategic:
            move = f"Focus on: {strategic[0].title}"
            top = [i.title for i in strategic[:3]]
        elif supportive:
            move = f"Advance: {supportive[0].title}"
            top = [i.title for i in supportive[:3]]
        else:
            move = "Evaluate current work for strategic alignment."
            top = []

        maintenance_tasks = [i.title for i in maintenance_inits[:3]]
        position_building = []
        if strategic:
            position_building.append(f"Ship visible artifact for {strategic[0].title}")
        position_building.append("Log influence interactions for the week")

        return WeeklySimulation(
            week_start=week_start,
            strategic_move=move,
            maintenance_tasks=maintenance_tasks or ["Review backlog"],
            position_building=position_building,
            influence_trend=influence_trend.get("direction", "flat"),
            optionality_trend="flat",
            top_initiatives=top,
            raw_analysis="Rule-based simulation (LLM unavailable)",
        )

    @staticmethod
    def _format_initiatives(initiatives: list) -> str:
        lines = []
        for i in initiatives:
            lines.append(
                f"- {i.title} [{i.category.value}] "
                f"(score: {i.scores.total}/25, visibility: {i.visibility.value}, "
                f"risk: {i.risk_level})"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_stakeholders(stakeholders: list) -> str:
        lines = []
        for s in stakeholders:
            lines.append(
                f"- {s.name} ({s.role}) — "
                f"influence: {s.influence_level}/10, "
                f"alignment: {s.alignment_score:+d}, "
                f"dependency: {s.dependency_on_you}/10, "
                f"trust: {s.trust_score}/10"
            )
        return "\n".join(lines)

    @staticmethod
    def _format_assets(assets: list) -> str:
        lines = []
        for a in assets:
            score = (
                f"rep={a.reputation_score:.1f}"
                if a.asset_type.value == "reputation"
                else f"opt={a.optionality_score:.1f}"
            )
            lines.append(
                f"- {a.title} [{a.asset_type.value}] "
                f"({score}, visibility: {a.visibility.value})"
            )
        return "\n".join(lines)
