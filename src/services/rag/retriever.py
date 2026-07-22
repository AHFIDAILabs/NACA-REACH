"""
RAG Retriever — Hybrid Vector + BM25 Knowledge Base Search

Retrieves relevant knowledge chunks using:
1. Dense vector similarity search (Qdrant/Vertex AI Vector Search)
2. Sparse BM25 keyword matching
3. Re-ranking for final top-K selection

See: System Design Section 3.2.3 (Retrieval Architecture)
"""

from typing import Optional

import structlog

from src.core.config import get_settings
from src.schemas.messages import RAGResult, RetrievedChunk

logger = structlog.get_logger()
settings = get_settings()


class RAGRetriever:
    """
    Hybrid retrieval system combining dense and sparse search.

    In the initial build, uses Qdrant for vector search.
    BM25 and re-ranking will be added in Step 06 (Knowledge Base Development).
    """

    def __init__(self):
        self._qdrant_client = None

    def _get_qdrant_client(self):
        """Lazy-load Qdrant client."""
        if self._qdrant_client is None:
            try:
                from qdrant_client import QdrantClient

                self._qdrant_client = QdrantClient(url=settings.qdrant_url)
                logger.info("qdrant_client_connected", url=settings.qdrant_url)
            except Exception as e:
                logger.error("qdrant_connection_failed", error=str(e))
                raise
        return self._qdrant_client

    async def retrieve(
        self,
        query: str,
        content_domain: Optional[str] = None,
        top_k: int = 5,
    ) -> RAGResult:
        """
        Retrieve the most relevant knowledge chunks for a query.

        Steps:
        1. Generate query embedding
        2. Search vector DB with optional domain filter
        3. Apply confidence threshold
        4. Return ranked results with source citations
        """
        try:
            # Generate embedding for the query
            query_vector = await self._embed_query(query)

            # Search Qdrant
            search_filter = None
            if content_domain:
                from qdrant_client.models import Filter, FieldCondition, MatchValue

                search_filter = Filter(
                    must=[
                        FieldCondition(
                            key="content_domain",
                            match=MatchValue(value=content_domain),
                        )
                    ]
                )

            client = self._get_qdrant_client()
            results = client.search(
                collection_name=settings.qdrant_collection,
                query_vector=query_vector,
                query_filter=search_filter,
                limit=top_k,
                with_payload=True,
                score_threshold=0.5,  # Minimum confidence threshold
            )

            chunks = []
            for result in results:
                payload = result.payload or {}
                chunks.append(
                    RetrievedChunk(
                        chunk_id=str(result.id),
                        document_id=payload.get("document_id", ""),
                        content=payload.get("content_text", ""),
                        content_domain=payload.get("content_domain", ""),
                        confidence_score=result.score,
                        source_title=payload.get("source_title", "Unknown"),
                        source_organisation=payload.get("source_organisation"),
                    )
                )

            avg_confidence = (
                sum(c.confidence_score for c in chunks) / len(chunks)
                if chunks
                else 0.0
            )

            logger.info(
                "rag_retrieval",
                query_length=len(query),
                domain=content_domain,
                results=len(chunks),
                avg_confidence=round(avg_confidence, 3),
            )

            return RAGResult(
                chunks=chunks,
                query_used=query,
                retrieval_method="vector",
                average_confidence=avg_confidence,
            )

        except Exception as e:
            logger.error("rag_retrieval_failed", error=str(e))
            return RAGResult(
                chunks=[],
                query_used=query,
                retrieval_method="vector",
                average_confidence=0.0,
            )

    _vertex_model = None
    _local_model = None

    async def _embed_query(self, query: str) -> list[float]:
        """
        Generate embedding vector using Vertex AI (cached model).
        Falls back to sentence-transformers if Vertex unavailable.
        """
        try:
            if RAGRetriever._vertex_model is None:
                from google.cloud import aiplatform
                import vertexai
                vertexai.init(
                    project=settings.gcp_project_id,
                    location=settings.gcp_region,
                )
                from vertexai.language_models import TextEmbeddingModel
                RAGRetriever._vertex_model = TextEmbeddingModel.from_pretrained(settings.embedding_model)
                logger.info("vertex_embedding_model_loaded", model=settings.embedding_model)

            embeddings = RAGRetriever._vertex_model.get_embeddings([query])
            return embeddings[0].values

        except Exception as e:
            logger.warning("vertex_embedding_failed_using_fallback", error=str(e))
            return await self._fallback_embed(query)

    async def _fallback_embed(self, query: str) -> list[float]:
        """Fallback: sentence-transformers for local development."""
        try:
            if RAGRetriever._local_model is None:
                from sentence_transformers import SentenceTransformer
                RAGRetriever._local_model = SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("local_embedding_model_loaded")

            embedding = RAGRetriever._local_model.encode(query).tolist()
            return embedding
        except Exception as e:
            logger.error("fallback_embedding_failed", error=str(e))
            return [0.0] * settings.embedding_dimensions
