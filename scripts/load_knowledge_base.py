#!/usr/bin/env python3
"""
NACA AI Chatbot — Knowledge Base Loader

Loads all documents from scripts/seed_data/knowledge_base/ into the
Qdrant vector database and BM25 index.

Supported formats: PDF, JSON (sample_knowledge_base.json), TXT, DOCX

Usage:
    PYTHONPATH=. py -3.11 scripts/load_knowledge_base.py

    Options:
        --reset     Delete existing collection and reload from scratch
        --dir PATH  Custom knowledge base directory (default: scripts/seed_data/knowledge_base)

Requires:
    - Qdrant running on localhost:6333
    - GOOGLE_APPLICATION_CREDENTIALS set for Vertex AI embeddings
    - pypdf installed (pip install pypdf)
"""

import asyncio
import json
import os
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("NACA_ENVIRONMENT", "development")

from src.core.config import get_settings
from src.services.rag.chunker import chunk_document
from src.services.rag.bm25_index import get_bm25_index

settings = get_settings()

# Domain classification based on filename keywords
DOMAIN_KEYWORDS = {
    "PREVENTION": ["prevention", "prev", "condom", "prep", "pep", "pmtct", "vmmc"],
    "ART_TREATMENT": ["treatment", "art", "arv", "adherence", "viral", "regimen"],
    "TESTING_SERVICES": ["testing", "test", "hts", "vct", "diagnosis", "ibbss"],
    "MYTH_CORRECTION": ["myth", "fact", "misconception", "stigma"],
    "CRISIS_SUPPORT": ["crisis", "mental", "support", "counselling", "emotional"],
    "FAQ": ["faq", "question", "answer"],
}


def classify_domain(filename: str) -> str:
    """Guess the content domain from the filename."""
    name_lower = filename.lower()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in name_lower:
                return domain
    # Default domain for general policy/programme documents
    return "PREVENTION"


def extract_source(filename: str) -> str:
    """Extract source organisation from filename."""
    name_lower = filename.lower()
    if "naca" in name_lower:
        return "NACA"
    if "who" in name_lower:
        return "WHO"
    if "fmoh" in name_lower or "national" in name_lower:
        return "FMOH"
    if "pepfar" in name_lower:
        return "PEPFAR"
    return "NACA"


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append(text.strip())
        full_text = "\n\n".join(pages)
        print(f"     Extracted {len(reader.pages)} pages, {len(full_text)} chars")
        return full_text
    except Exception as e:
        print(f"     ⚠️  PDF extraction failed: {e}")
        return ""


def extract_text_from_json(file_path: str) -> list[dict]:
    """Extract documents from the sample_knowledge_base.json format."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("documents", [])


def load_files_from_directory(directory: str) -> list[dict]:
    """
    Scan directory for all supported files and prepare document records.
    Returns list of {title, domain, source, content, filename}
    """
    documents = []
    dir_path = Path(directory)

    if not dir_path.exists():
        print(f"❌ Directory not found: {directory}")
        return []

    supported_extensions = {".pdf", ".txt", ".json", ".docx"}
    files = sorted(dir_path.iterdir())

    for file_path in files:
        if file_path.is_dir():
            continue
        if file_path.suffix.lower() not in supported_extensions:
            print(f"  ⏭️  Skipping unsupported file: {file_path.name}")
            continue

        print(f"\n  📄 Processing: {file_path.name}")

        if file_path.suffix.lower() == ".json":
            # Handle the structured JSON format
            json_docs = extract_text_from_json(str(file_path))
            for jdoc in json_docs:
                documents.append({
                    "title": jdoc["title"],
                    "domain": jdoc.get("domain", "PREVENTION"),
                    "source": jdoc.get("source", "NACA"),
                    "content": jdoc["content"],
                    "filename": file_path.name,
                })
            print(f"     Loaded {len(json_docs)} documents from JSON")

        elif file_path.suffix.lower() == ".pdf":
            content = extract_text_from_pdf(str(file_path))
            if content and len(content) > 100:
                # Clean up the title from filename
                title = file_path.stem.replace("-", " ").replace("_", " ").strip()
                title = " ".join(w.capitalize() if len(w) > 3 else w for w in title.split())
                documents.append({
                    "title": title,
                    "domain": classify_domain(file_path.name),
                    "source": extract_source(file_path.name),
                    "content": content,
                    "filename": file_path.name,
                })
            else:
                print(f"     ⚠️  Skipped (no extractable text or too short)")

        elif file_path.suffix.lower() == ".txt":
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            if content and len(content) > 100:
                title = file_path.stem.replace("-", " ").replace("_", " ").strip()
                documents.append({
                    "title": title,
                    "domain": classify_domain(file_path.name),
                    "source": extract_source(file_path.name),
                    "content": content,
                    "filename": file_path.name,
                })

        elif file_path.suffix.lower() == ".docx":
            try:
                import docx
                doc = docx.Document(str(file_path))
                content = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
                if content and len(content) > 100:
                    title = file_path.stem.replace("-", " ").replace("_", " ").strip()
                    documents.append({
                        "title": title,
                        "domain": classify_domain(file_path.name),
                        "source": extract_source(file_path.name),
                        "content": content,
                        "filename": file_path.name,
                    })
            except ImportError:
                print(f"     ⚠️  python-docx not installed, skipping DOCX")
            except Exception as e:
                print(f"     ⚠️  DOCX extraction failed: {e}")

    return documents


def get_embedder():
    """Get the embedding function — Vertex AI or fallback to sentence-transformers."""
    # Try Vertex AI first
    try:
        import vertexai
        from vertexai.language_models import TextEmbeddingModel

        project = settings.gcp_project_id
        region = settings.gcp_region

        vertexai.init(project=project, location=region)
        model = TextEmbeddingModel.from_pretrained(settings.embedding_model)

        # Test it works
        test = model.get_embeddings(["test"])
        dim = len(test[0].values)
        print(f"✅ Using Vertex AI embeddings ({settings.embedding_model}, {dim} dims)")

        def embed_fn(texts):
            # Vertex AI has 20k token limit per request
            # Each chunk is ~500-1000 tokens, so batch 5 at a time
            all_embeddings = []
            for i in range(0, len(texts), 5):
                batch = texts[i:i+5]
                results = model.get_embeddings(batch)
                all_embeddings.extend([r.values for r in results])
            return all_embeddings, dim

        return embed_fn

    except Exception as e:
        print(f"⚠️  Vertex AI failed ({e}), trying sentence-transformers...")

    # Fallback to local model
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        dim = 384
        print(f"✅ Using local embeddings (all-MiniLM-L6-v2, {dim} dims)")

        def embed_fn(texts):
            embeddings = model.encode(texts)
            return [e.tolist() for e in embeddings], dim

        return embed_fn

    except ImportError:
        print("❌ No embedding model available. Install sentence-transformers or configure Vertex AI.")
        sys.exit(1)


async def main():
    parser = argparse.ArgumentParser(description="Load knowledge base into Qdrant")
    parser.add_argument("--reset", action="store_true", help="Delete and recreate collection")
    parser.add_argument("--dir", default="scripts/seed_data/knowledge_base",
                        help="Knowledge base directory path")
    args = parser.parse_args()

    kb_dir = args.dir
    print(f"{'='*60}")
    print(f"📚 NACA-REACH Knowledge Base Loader")
    print(f"{'='*60}")
    print(f"   Directory: {kb_dir}")
    print()

    # ── Load documents ──
    documents = load_files_from_directory(kb_dir)

    if not documents:
        print("\n❌ No documents found. Check the directory path.")
        return

    print(f"\n{'='*60}")
    print(f"   Found {len(documents)} documents to process")
    print(f"{'='*60}")

    # ── Get embedding function ──
    embed_fn = get_embedder()

    # ── Connect to Qdrant ──
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct

    try:
        client = QdrantClient(url=settings.qdrant_url)
        client.get_collections()
        print(f"✅ Connected to Qdrant at {settings.qdrant_url}")
    except Exception as e:
        print(f"❌ Cannot connect to Qdrant: {e}")
        return

    # ── Create or reset collection ──
    # Get embedding dimensions from a test embed
    test_embeddings, embed_dim = embed_fn(["test"])

    if args.reset:
        try:
            client.delete_collection(settings.qdrant_collection)
            print(f"   Deleted existing collection: {settings.qdrant_collection}")
        except Exception:
            pass

    try:
        client.get_collection(settings.qdrant_collection)
        print(f"   Using existing collection: {settings.qdrant_collection}")
    except Exception:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=embed_dim, distance=Distance.COSINE),
        )
        print(f"   Created collection: {settings.qdrant_collection} ({embed_dim} dims)")

    # ── Process and index documents ──
    bm25 = get_bm25_index()
    total_chunks = 0
    total_start = time.time()

    for doc_idx, doc in enumerate(documents):
        title = doc["title"]
        domain = doc["domain"]
        content = doc["content"]
        source = doc["source"]

        print(f"\n  [{doc_idx+1}/{len(documents)}] {title}")
        print(f"     Domain: {domain} | Source: {source} | Content: {len(content)} chars")

        # Chunk the document
        chunks = chunk_document(content)
        if not chunks:
            print(f"     ⚠️  No chunks produced, skipping")
            continue

        print(f"     Chunks: {len(chunks)} | Avg tokens: {sum(c.token_count for c in chunks)//len(chunks)}")

        # Generate embeddings for all chunks at once (batch)
        chunk_texts = [c.content for c in chunks]
        try:
            embeddings, _ = embed_fn(chunk_texts)
        except Exception as e:
            print(f"     ⚠️  Embedding failed: {e}, skipping document")
            continue

        # Upsert into Qdrant
        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            point_id = total_chunks + i
            chunk_id = f"{domain.lower()}:{doc_idx}:{i}"

            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "chunk_id": chunk_id,
                    "document_id": f"doc_{doc_idx}",
                    "content_text": chunk.content,
                    "content_domain": domain,
                    "source_title": title,
                    "source_organisation": source,
                    "token_count": chunk.token_count,
                    "language": "en",
                    "filename": doc.get("filename", ""),
                },
            ))

            # Add to BM25 index
            bm25.add_document(
                chunk_id=chunk_id,
                content=chunk.content,
                metadata={
                    "content_domain": domain,
                    "source_title": title,
                    "source_organisation": source,
                },
            )

        # Batch upsert to Qdrant
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i+batch_size]
            client.upsert(
                collection_name=settings.qdrant_collection,
                points=batch,
            )

        total_chunks += len(chunks)
        print(f"     ✅ Indexed {len(chunks)} chunks")

    # Build BM25 index
    bm25.build()

    elapsed = time.time() - total_start
    info = client.get_collection(settings.qdrant_collection)

    print(f"\n{'='*60}")
    print(f"✅ Knowledge base loaded successfully!")
    print(f"   Documents processed: {len(documents)}")
    print(f"   Total chunks:        {total_chunks}")
    print(f"   Qdrant vectors:      {info.points_count}")
    print(f"   BM25 index docs:     {bm25.size}")
    print(f"   Time elapsed:        {elapsed:.1f}s")
    print(f"{'='*60}")

    # Show domain breakdown
    print(f"\n   Domain breakdown:")
    domain_counts = {}
    for doc in documents:
        d = doc["domain"]
        domain_counts[d] = domain_counts.get(d, 0) + 1
    for domain, count in sorted(domain_counts.items()):
        print(f"     {domain}: {count} documents")


if __name__ == "__main__":
    asyncio.run(main())