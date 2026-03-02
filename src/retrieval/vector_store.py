"""Qdrant Cloud vector store operations."""

import structlog
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, VectorParams

from src.core.exceptions import RetrievalError

log = structlog.get_logger(__name__)

VECTOR_SIZE = 384  # all-MiniLM-L6-v2 output dimension


class VectorStore:
    """Qdrant Cloud vector store for brain entry embeddings."""

    def __init__(self, url: str, api_key: str, collection_name: str) -> None:
        self.collection_name = collection_name
        self.entity_collection_name = f"{collection_name}_entities"
        self.client = QdrantClient(url=url, api_key=api_key, timeout=10)

    async def init_collection(self) -> None:
        """Create entry and entity collections if they don't exist."""
        for coll_name in [self.collection_name, self.entity_collection_name]:
            try:
                collections = self.client.get_collections().collections
                exists = any(c.name == coll_name for c in collections)
                if not exists:
                    self.client.create_collection(
                        collection_name=coll_name,
                        vectors_config=VectorParams(
                            size=VECTOR_SIZE, distance=Distance.COSINE
                        ),
                    )
                    log.info(
                        "qdrant_collection_created",
                        collection=coll_name,
                    )
                else:
                    log.info(
                        "qdrant_collection_exists",
                        collection=coll_name,
                    )
            except Exception as e:
                log.error("qdrant_init_failed", collection=coll_name, error=str(e))
                raise RetrievalError(
                    "Failed to initialize Qdrant collection",
                    details={"collection": coll_name, "error": str(e)},
                ) from e

    async def upsert(
        self, id: str, vector: list[float], payload: dict
    ) -> None:
        """Store or update a vector with metadata."""
        try:
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=id,
                        vector=vector,
                        payload=payload,
                    )
                ],
            )
            log.debug("vector_upserted", entry_id=id)
        except Exception as e:
            log.error("vector_upsert_failed", entry_id=id, error=str(e))
            raise RetrievalError(
                "Failed to upsert vector",
                details={"entry_id": id, "error": str(e)},
            ) from e

    async def search(
        self, query_vector: list[float], limit: int = 20
    ) -> list[tuple[str, float]]:
        """Search for similar vectors. Returns (entry_id, score) pairs."""
        try:
            results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
            )
            return [
                (str(point.id), point.score)
                for point in results.points
            ]
        except Exception as e:
            log.error("vector_search_failed", error=str(e))
            raise RetrievalError(
                "Vector search failed",
                details={"error": str(e)},
            ) from e

    # ── Entity vector operations ─────────────────────────────────

    async def upsert_entity(
        self, id: str, vector: list[float], payload: dict
    ) -> None:
        """Store or update an entity vector with metadata."""
        try:
            self.client.upsert(
                collection_name=self.entity_collection_name,
                points=[
                    PointStruct(
                        id=id,
                        vector=vector,
                        payload=payload,
                    )
                ],
            )
            log.debug("entity_vector_upserted", entity_id=id)
        except Exception as e:
            log.error("entity_vector_upsert_failed", entity_id=id, error=str(e))
            raise RetrievalError(
                "Failed to upsert entity vector",
                details={"entity_id": id, "error": str(e)},
            ) from e

    async def search_entities(
        self, query_vector: list[float], limit: int = 10
    ) -> list[tuple[str, float]]:
        """Search for similar entity vectors. Returns (entity_id, score) pairs."""
        try:
            results = self.client.query_points(
                collection_name=self.entity_collection_name,
                query=query_vector,
                limit=limit,
            )
            return [
                (str(point.id), point.score)
                for point in results.points
            ]
        except Exception as e:
            log.error("entity_vector_search_failed", error=str(e))
            raise RetrievalError(
                "Entity vector search failed",
                details={"error": str(e)},
            ) from e
