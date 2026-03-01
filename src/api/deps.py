"""Shared application dependencies — breaks circular import between main and routes."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

from src.classification.classifier import Classifier
from src.core.pipeline import CapturePipeline
from src.retrieval.search import SearchOrchestrator
from src.storage.database import Database
from src.storage.repository import BrainEntryRepository


class AppState:
    """Container for application-wide service instances."""

    pipeline: CapturePipeline
    repository: BrainEntryRepository
    search: SearchOrchestrator
    classifier: Classifier
    database: Database


app_state = AppState()

# Templates
template_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(template_dir))
