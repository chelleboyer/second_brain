"""FastAPI application — Second Brain MVP."""

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
import uvicorn
from fastapi import FastAPI
from slack_sdk import WebClient

from src.api.deps import app_state
from src.classification.classifier import Classifier
from src.classification.provider import HuggingFaceProvider
from src.config import get_settings
from src.core.pipeline import CapturePipeline
from src.retrieval.keyword_search import KeywordSearch
from src.retrieval.search import SearchOrchestrator
from src.retrieval.vector_store import VectorStore
from src.slack.collector import SlackCollector
from src.storage.database import Database
from src.storage.repository import BrainEntryRepository


def configure_logging(log_level: str = "INFO") -> None:
    """Configure structlog with JSON (production) or console (dev) output."""
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if log_level == "DEBUG":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    import logging

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application startup and shutdown lifecycle."""
    log = structlog.get_logger("lifespan")
    settings = get_settings()

    configure_logging(settings.LOG_LEVEL)
    log.info("starting_up", db_path=str(settings.resolved_db_path))

    # Initialize database
    database = Database(str(settings.resolved_db_path))
    await database.init_db()
    app_state.database = database
    log.info("database_initialized")

    # Initialize repository
    repository = BrainEntryRepository(database)
    app_state.repository = repository

    # Initialize LLM provider + classifier
    provider = HuggingFaceProvider(
        api_token=settings.HF_API_TOKEN,
        classification_model=settings.HF_CLASSIFICATION_MODEL,
        embedding_model=settings.HF_EMBEDDING_MODEL,
    )
    classifier = Classifier(provider)
    app_state.classifier = classifier

    # Initialize vector store
    vector_store = VectorStore(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
        collection_name=settings.QDRANT_COLLECTION_NAME,
    )
    await vector_store.init_collection()
    log.info("vector_store_initialized")

    # Initialize keyword search
    keyword_search = KeywordSearch(repository)

    # Initialize search orchestrator
    search_orchestrator = SearchOrchestrator(
        vector_store=vector_store,
        keyword_search=keyword_search,
        provider=provider,
        repository=repository,
    )
    app_state.search = search_orchestrator

    # Initialize Slack collector
    slack_client = WebClient(token=settings.SLACK_BOT_TOKEN)
    collector = SlackCollector(
        client=slack_client,
        channel_id=settings.SLACK_CHANNEL_ID,
        repository=repository,
        collect_dms=settings.SLACK_COLLECT_DMS,
    )

    # Initialize capture pipeline
    pipeline = CapturePipeline(
        classifier=classifier,
        repository=repository,
        vector_store=vector_store,
        collector=collector,
    )
    app_state.pipeline = pipeline

    # Run startup catch-up in background so UI is immediately available
    async def _background_catch_up() -> None:
        log.info("catch_up_starting")
        try:
            processed, failed = await pipeline.catch_up()
            log.info("catch_up_complete", processed=processed, failed=failed)
        except Exception as e:
            log.error("catch_up_failed", error=str(e), exc_info=True)

    catch_up_task = asyncio.create_task(_background_catch_up())

    yield

    # Shutdown — cancel catch-up if still running
    if not catch_up_task.done():
        catch_up_task.cancel()
        try:
            await catch_up_task
        except asyncio.CancelledError:
            pass
    log.info("shutting_down")


# Create FastAPI app
app = FastAPI(title="Second Brain", lifespan=lifespan)

# Include routes
from src.api.routes import router  # noqa: E402

app.include_router(router)


def run() -> None:
    """Entry point for running the application."""
    uvicorn.run(
        "src.main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()
