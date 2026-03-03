"""Shared application dependencies — breaks circular import between main and routes."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from src.classification.classifier import Classifier
from src.core.entity_resolution import EntityRepository, EntityResolver
from src.core.evaluation import MoveEvaluationEngine
from src.core.graph import GraphService
from src.core.pipeline import CapturePipeline
from src.core.simulation import InfluenceTracker, StrategicSimulator
from src.core.suggestions import SuggestionEngine
from src.core.summarization import SummarizationService
from src.retrieval.recall import RecallService
from src.retrieval.search import SearchOrchestrator
from src.slack.commands import SlackCommandHandler
from src.storage.database import Database
from src.storage.repository import BrainEntryRepository
from src.storage.strategy_repository import StrategyRepository


class AppState:
    """Container for application-wide service instances."""

    pipeline: CapturePipeline
    repository: BrainEntryRepository
    search: SearchOrchestrator
    recall: RecallService
    classifier: Classifier
    database: Database
    entity_repo: EntityRepository
    entity_resolver: EntityResolver
    # Phase 1: Intelligence layer
    graph_service: GraphService
    suggestion_engine: SuggestionEngine
    summarization_service: SummarizationService
    slack_commands: SlackCommandHandler
    # Phase II: Strategic Positioning Engine
    strategy_repo: StrategyRepository
    evaluation_engine: MoveEvaluationEngine
    influence_tracker: InfluenceTracker
    strategic_simulator: StrategicSimulator


app_state = AppState()

# Templates
template_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))
