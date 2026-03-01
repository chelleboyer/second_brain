"""Custom exception hierarchy for Second Brain."""


class SecondBrainError(Exception):
    """Base exception for all Second Brain errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class ClassificationError(SecondBrainError):
    """Error during message classification or extraction."""


class StorageError(SecondBrainError):
    """Error during database operations."""


class RetrievalError(SecondBrainError):
    """Error during search or retrieval operations."""


class SlackCollectionError(SecondBrainError):
    """Error during Slack message collection."""


class ProviderError(SecondBrainError):
    """Error communicating with an external provider (HF, Qdrant, etc.)."""
