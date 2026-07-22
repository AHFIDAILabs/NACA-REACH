"""
NACA AI Chatbot — Document Ingestion Pipeline (Section 3.2.2)

Full pipeline for processing source documents into the knowledge base:
1. Upload → 2. Parse/extract text → 3. Clean → 4. Chunk →
5. Tag metadata → 6. Embed → 7. Index in Vector DB →
8. Build BM25 index → 9. Quality review

Supports PDF, DOCX, TXT source formats.
Knowledge base stored in English (translation at response layer only).
"""

import uuid
from datetime import datetime
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.services.rag.chunker import chunk_document, extract_text_from_file, DocumentChunk
from src.services.rag.embedder import EmbeddingService
from src.services.rag.bm25_index import BM25Index, get_bm25_index

logger = structlog.get_logger()
settings = get_settings()


class DocumentIngestionPipeline:
    """
    Processes source documents into the knowledge base.

    Flow:
    1. Extract text from uploaded file
    2. Clean and normalise text
    3. Chunk into 512–1024 token segments with 10% overlap
    4. Generate embeddings (Vertex AI text-embedding-004)
    5. Upsert vectors into Qdrant with metadata
    6. Store chunk records in PostgreSQL
    7. Add to BM25 index
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.embedder = EmbeddingService()
        self._qdrant = None

    def _get_qdrant(self):
        if self._qdrant is None:
            from qdrant_client import QdrantClient
            self._qdrant = QdrantClient(url=settings.qdrant_url)
        return self._qdrant

    async def ingest_document(
        self,
        file_path: str,
        title: str,
        content_domain: str,
        source_organisation: str = "NACA",
        uploaded_by: str = "system",
    ) -> dict:
        """
        Full ingestion pipeline for a single document.
        Returns a status dict with processing results.
        """
        doc_id = str(uuid.uuid4())
        logger.info(
            "ingestion_started",
            doc_id=doc_id,
            title=title,
            domain=content_domain,
            file=file_path,
        )

        try:
            # ── Step 1: Extract text ──
            raw_text = extract_text_from_file(file_path)
            if not raw_text or len(raw_text.strip()) < 50:
                return {"status": "failed", "error": "No extractable text found", "doc_id": doc_id}

            # ── Step 2: Clean text ──
            cleaned_text = self._clean_text(raw_text)

            # ── Step 3: Chunk ──
            chunks = chunk_document(cleaned_text)
            if not chunks:
                return {"status": "failed", "error": "No chunks produced", "doc_id": doc_id}

            # ── Step 4: Generate embeddings ──
            chunk_texts = [c.content for c in chunks]
            embeddings = await self.embedder.embed_batch(chunk_texts)

            # ── Step 5: Upsert into Qdrant ──
            await self._upsert_vectors(
                doc_id=doc_id,
                chunks=chunks,
                embeddings=embeddings,
                title=title,
                content_domain=content_domain,
                source_organisation=source_organisation,
            )

            # ── Step 6: Store in PostgreSQL ──
            await self._store_document_record(
                doc_id=doc_id,
                title=title,
                file_path=file_path,
                content_domain=content_domain,
                source_organisation=source_organisation,
                chunk_count=len(chunks),
                uploaded_by=uploaded_by,
            )

            await self._store_chunk_records(
                doc_id=doc_id,
                chunks=chunks,
                content_domain=content_domain,
            )

            # ── Step 7: Add to BM25 index ──
            bm25 = get_bm25_index()
            for i, chunk in enumerate(chunks):
                chunk_id = f"{doc_id}:{i}"
                bm25.add_document(
                    chunk_id=chunk_id,
                    content=chunk.content,
                    metadata={
                        "document_id": doc_id,
                        "content_domain": content_domain,
                        "source_title": title,
                    },
                )

            bm25.build()

            logger.info(
                "ingestion_completed",
                doc_id=doc_id,
                chunks=len(chunks),
                total_tokens=sum(c.token_count for c in chunks),
            )

            return {
                "status": "indexed",
                "doc_id": doc_id,
                "title": title,
                "chunks_created": len(chunks),
                "total_tokens": sum(c.token_count for c in chunks),
            }

        except Exception as e:
            logger.error("ingestion_failed", doc_id=doc_id, error=str(e), exc_info=True)
            return {"status": "failed", "error": str(e), "doc_id": doc_id}

    def _clean_text(self, text: str) -> str:
        """Clean and normalise extracted text."""
        import re

        # Normalise whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        # Normalise line breaks
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Remove page numbers / headers / footers (common in PDFs)
        text = re.sub(r'\n\s*Page \d+ of \d+\s*\n', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
        # Remove non-printable characters
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

        return text.strip()

    async def _upsert_vectors(
        self,
        doc_id: str,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        title: str,
        content_domain: str,
        source_organisation: str,
    ):
        """Upsert chunk vectors into Qdrant with metadata payloads."""
        from qdrant_client.models import PointStruct

        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = f"{doc_id}:{i}"
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "document_id": doc_id,
                        "chunk_index": i,
                        "content_text": chunk.content,
                        "content_domain": content_domain,
                        "source_title": title,
                        "source_organisation": source_organisation,
                        "token_count": chunk.token_count,
                        "language": "en",
                        "indexed_at": datetime.utcnow().isoformat(),
                    },
                )
            )

        client = self._get_qdrant()

        # Ensure collection exists
        try:
            client.get_collection(settings.qdrant_collection)
        except Exception:
            from qdrant_client.models import Distance, VectorParams
            client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=VectorParams(
                    size=settings.embedding_dimensions,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("qdrant_collection_created", name=settings.qdrant_collection)

        # Batch upsert
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            client.upsert(
                collection_name=settings.qdrant_collection,
                points=batch,
            )

        logger.info("vectors_upserted", doc_id=doc_id, count=len(points))

    async def _store_document_record(
        self, doc_id, title, file_path, content_domain,
        source_organisation, chunk_count, uploaded_by,
    ):
        """Store document metadata in PostgreSQL."""
        from sqlalchemy import text

        await self.db.execute(
            text("""
                INSERT INTO knowledge_documents
                    (document_id, title, file_name, file_path, file_size_bytes,
                     content_domain, source_organisation, status, chunk_count,
                     language, uploaded_by, created_at, updated_at)
                VALUES
                    (:doc_id, :title, :file_name, :file_path, :file_size,
                     :domain, :source_org, 'INDEXED', :chunks,
                     'en', :uploaded_by, NOW(), NOW())
            """),
            {
                "doc_id": doc_id,
                "title": title,
                "file_name": Path(file_path).name,
                "file_path": file_path,
                "file_size": Path(file_path).stat().st_size if Path(file_path).exists() else 0,
                "domain": content_domain,
                "source_org": source_organisation,
                "chunks": chunk_count,
                "uploaded_by": uploaded_by,
            },
        )

    async def _store_chunk_records(self, doc_id, chunks, content_domain):
        """Store chunk metadata in PostgreSQL (vector IDs for traceability)."""
        from sqlalchemy import text

        for i, chunk in enumerate(chunks):
            await self.db.execute(
                text("""
                    INSERT INTO document_chunks
                        (chunk_id, document_id, chunk_index, content_text,
                         token_count, content_domain, language, vector_id,
                         embedding_model, created_at)
                    VALUES
                        (:chunk_id, :doc_id, :idx, :content,
                         :tokens, :domain, 'en', :vector_id,
                         :model, NOW())
                """),
                {
                    "chunk_id": str(uuid.uuid4()),
                    "doc_id": doc_id,
                    "idx": i,
                    "content": chunk.content,
                    "tokens": chunk.token_count,
                    "domain": content_domain,
                    "vector_id": f"{doc_id}:{i}",
                    "model": settings.embedding_model,
                },
            )
