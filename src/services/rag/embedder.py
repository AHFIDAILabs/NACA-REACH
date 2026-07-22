"""
NACA AI Chatbot — Embedding Service (Section 3.2.2)

Generates vector embeddings using Google text-embedding-004 (Vertex AI).
Supports batch embedding for document ingestion and single-query embedding
for retrieval-time queries.
"""

import hashlib
from functools import lru_cache

import structlog

from src.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class EmbeddingService:
    """
    Generates text embeddings using Vertex AI (text-embedding-004).
    Falls back to a local sentence-transformers model for development.
    """

    def __init__(self):
        self._vertex_model = None
        self._local_model = None
        self._cache: dict[str, list[float]] = {}

    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single query. Uses cache for repeated queries."""
        cache_key = hashlib.md5(text.encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        embedding = await self._generate_embedding(text)
        self._cache[cache_key] = embedding

        # Keep cache bounded
        if len(self._cache) > 1000:
            oldest = list(self._cache.keys())[:500]
            for k in oldest:
                del self._cache[k]

        return embedding

    async def embed_batch(self, texts: list[str], batch_size: int = 50) -> list[list[float]]:
        """
        Generate embeddings for a batch of texts.
        Used during document ingestion for bulk embedding.
        Processes in batches to respect API rate limits.
        """
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = await self._generate_batch(batch)
            all_embeddings.extend(batch_embeddings)
            logger.info(
                "embedding_batch_progress",
                processed=min(i + batch_size, len(texts)),
                total=len(texts),
            )

        return all_embeddings

    async def _generate_embedding(self, text: str) -> list[float]:
        """Generate a single embedding vector."""
        result = await self._generate_batch([text])
        return result[0]

    async def _generate_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings via Vertex AI or fallback."""
        # Try Vertex AI first
        try:
            return self._vertex_embed(texts)
        except Exception as e:
            logger.warning("vertex_embedding_failed", error=str(e))

        # Fallback to local model
        try:
            return self._local_embed(texts)
        except Exception as e:
            logger.error("all_embedding_methods_failed", error=str(e))
            # Return zero vectors as last resort
            return [[0.0] * settings.embedding_dimensions for _ in texts]

    def _vertex_embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using Vertex AI text-embedding-004."""
        from google.cloud import aiplatform
        from vertexai.language_models import TextEmbeddingModel

        if not self._vertex_model:
            aiplatform.init(
                project=settings.gcp_project_id,
                location=settings.gcp_region,
            )
            self._vertex_model = TextEmbeddingModel.from_pretrained(
                settings.embedding_model
            )

        embeddings = self._vertex_model.get_embeddings(texts)
        return [e.values for e in embeddings]

    def _local_embed(self, texts: list[str]) -> list[list[float]]:
        """Fallback: sentence-transformers for local development."""
        if not self._local_model:
            from sentence_transformers import SentenceTransformer
            self._local_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("loaded_local_embedding_model", model="all-MiniLM-L6-v2")

        embeddings = self._local_model.encode(texts)
        return [e.tolist() for e in embeddings]
