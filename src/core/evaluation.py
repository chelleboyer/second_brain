"""Move Evaluation Engine — scores initiatives for strategic alignment."""

import structlog

from src.models.enums import InitiativeCategory, InitiativeType, VisibilityLevel
from src.models.strategy import (
    Initiative,
    InitiativeCreate,
    InitiativeScores,
)
from src.storage.strategy_repository import StrategyRepository

log = structlog.get_logger(__name__)


# ── Move Evaluation Constants ────────────────────────────────────

MOVE_QUESTIONS: list[dict[str, str]] = [
    {
        "key": "authority",
        "question": "Does this increase authority?",
        "help": "Will people see you as more knowledgeable or essential?",
    },
    {
        "key": "asymmetric_info",
        "question": "Does this increase asymmetric information?",
        "help": "Will you learn things others don't know?",
    },
    {
        "key": "future_mobility",
        "question": "Does this increase future mobility?",
        "help": "Will this be valued outside your current role?",
    },
    {
        "key": "reusable_leverage",
        "question": "Does this create reusable leverage?",
        "help": "Can this be applied again in other contexts?",
    },
    {
        "key": "right_visibility",
        "question": "Is this visible to the right players?",
        "help": "Will decision-makers see or hear about this?",
    },
]


class MoveEvaluationEngine:
    """Evaluates initiatives using the 5-question strategic scoring framework.

    Projects scoring <12 → Maintenance
    Projects scoring 12–17 → Supportive
    Projects scoring 18+ → Strategic Move
    """

    def __init__(self, strategy_repo: StrategyRepository) -> None:
        self.strategy_repo = strategy_repo

    async def evaluate_initiative(
        self, create: InitiativeCreate
    ) -> Initiative:
        """Score and persist a new initiative.

        For scored initiatives, auto-computes category from scores.
        For mandatory initiatives, category defaults to maintenance
        (scores are ignored — value comes from linked relationships).
        """
        scores = InitiativeScores(
            authority=create.authority,
            asymmetric_info=create.asymmetric_info,
            future_mobility=create.future_mobility,
            reusable_leverage=create.reusable_leverage,
            right_visibility=create.right_visibility,
        )

        if create.initiative_type == InitiativeType.MANDATORY:
            category = scores.category if scores.total > 0 else InitiativeCategory.MAINTENANCE
        else:
            category = scores.category

        initiative = Initiative(
            title=create.title,
            description=create.description,
            initiative_type=create.initiative_type,
            scores=scores,
            category=category,
            visibility=create.visibility,
            risk_level=create.risk_level,
            notes=create.notes,
        )

        saved = await self.strategy_repo.save_initiative(initiative)
        log.info(
            "initiative_evaluated",
            id=str(saved.id),
            title=saved.title,
            total=scores.total,
            category=saved.category.value,
            initiative_type=saved.initiative_type.value,
        )
        return saved

    async def re_evaluate(self, initiative: Initiative) -> Initiative:
        """Re-compute category based on current scores and persist."""
        initiative.category = initiative.scores.category
        saved = await self.strategy_repo.save_initiative(initiative)
        log.info(
            "initiative_re_evaluated",
            id=str(saved.id),
            total=initiative.scores.total,
            category=saved.category.value,
        )
        return saved

    async def get_strategic_moves(self) -> list[Initiative]:
        """Return all active initiatives categorized as strategic."""
        return await self.strategy_repo.list_initiatives(
            status="active", category=InitiativeCategory.STRATEGIC
        )

    async def get_category_breakdown(self) -> dict[str, list[Initiative]]:
        """Group active initiatives by category."""
        all_active = await self.strategy_repo.list_initiatives(status="active")
        breakdown: dict[str, list[Initiative]] = {
            "strategic": [],
            "supportive": [],
            "maintenance": [],
        }
        for init in all_active:
            breakdown[init.category.value].append(init)
        return breakdown

    async def get_visibility_matrix(self) -> dict[str, int]:
        """Count active initiatives by visibility level."""
        all_active = await self.strategy_repo.list_initiatives(status="active")
        matrix = {v.value: 0 for v in VisibilityLevel}
        for init in all_active:
            matrix[init.visibility.value] += 1
        return matrix

    @staticmethod
    def get_questions() -> list[dict[str, str]]:
        """Return the five evaluation questions for UI rendering."""
        return MOVE_QUESTIONS
