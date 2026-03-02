"""Application configuration via environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Slack
    SLACK_BOT_TOKEN: str
    SLACK_CHANNEL_ID: str
    SLACK_COLLECT_DMS: bool = True

    # Hugging Face Inference API
    HF_API_TOKEN: str
    HF_CLASSIFICATION_MODEL: str = "meta-llama/Llama-3.1-8B-Instruct"
    HF_EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"

    # Qdrant Cloud
    QDRANT_URL: str
    QDRANT_API_KEY: str
    QDRANT_COLLECTION_NAME: str = "brain_entries"

    # App
    LOG_LEVEL: str = "INFO"
    DB_PATH: str = "second_brain.db"

    # Phase 2: Entity matching thresholds (per entity type)
    ENTITY_SIMILARITY_THRESHOLD_DEFAULT: float = 0.70
    ENTITY_SIMILARITY_THRESHOLD_PERSON: float = 0.80
    ENTITY_SIMILARITY_THRESHOLD_TECHNOLOGY: float = 0.75
    ENTITY_SIMILARITY_THRESHOLD_PROJECT: float = 0.75
    ENTITY_SIMILARITY_THRESHOLD_CONCEPT: float = 0.65
    ENTITY_SIMILARITY_THRESHOLD_ORGANIZATION: float = 0.75

    @property
    def resolved_db_path(self) -> Path:
        """Resolve DB_PATH to an absolute path relative to project root."""
        db_path = Path(self.DB_PATH)
        if db_path.is_absolute():
            return db_path
        # Resolve relative to project root (parent of src/)
        project_root = Path(__file__).resolve().parent.parent
        return project_root / db_path


@lru_cache
def get_settings() -> Settings:
    """Singleton settings instance."""
    return Settings()
