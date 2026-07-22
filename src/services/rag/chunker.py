"""
NACA AI Chatbot — Document Chunker (Section 3.2.2)

Splits source documents into semantic chunks (512–1024 tokens with 10% overlap)
for embedding and vector indexing. Handles PDF, DOCX, and TXT formats.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

logger = structlog.get_logger()

# Approximate tokens per character (English text)
CHARS_PER_TOKEN = 4
MIN_CHUNK_TOKENS = 512
MAX_CHUNK_TOKENS = 1024
OVERLAP_RATIO = 0.10


@dataclass
class DocumentChunk:
    """A single chunk of document text with metadata."""
    content: str
    chunk_index: int
    token_count: int
    metadata: dict = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """Rough token estimate from character count."""
    return len(text) // CHARS_PER_TOKEN


def extract_text_from_file(file_path: str) -> str:
    """
    Extract plain text from PDF, DOCX, or TXT files.
    Called during the document upload ingestion flow.
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".txt":
        return path.read_text(encoding="utf-8")

    elif suffix == ".docx":
        try:
            import docx
            doc = docx.Document(file_path)
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            logger.warning("python-docx_not_installed_falling_back_to_raw")
            return path.read_text(encoding="utf-8", errors="ignore")

    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
        except ImportError:
            logger.error("pypdf_not_installed")
            return ""

    else:
        # Attempt plain text read
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("text_extraction_failed", path=file_path, error=str(e))
            return ""


def chunk_document(
    text: str,
    min_tokens: int = MIN_CHUNK_TOKENS,
    max_tokens: int = MAX_CHUNK_TOKENS,
    overlap_ratio: float = OVERLAP_RATIO,
) -> list[DocumentChunk]:
    """
    Split document text into semantic chunks with overlap.

    Strategy:
    1. Split on paragraph boundaries first (double newlines)
    2. Merge small paragraphs into chunks up to max_tokens
    3. Split oversized paragraphs at sentence boundaries
    4. Add overlap between consecutive chunks
    """
    if not text or not text.strip():
        return []

    # Clean and normalise
    text = re.sub(r'\n{3,}', '\n\n', text.strip())
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    # Split oversized paragraphs into sentences
    segments = []
    for para in paragraphs:
        if estimate_tokens(para) > max_tokens:
            sentences = _split_sentences(para)
            segments.extend(sentences)
        else:
            segments.append(para)

    # Merge segments into chunks of target size
    chunks = []
    current_parts = []
    current_tokens = 0

    for segment in segments:
        seg_tokens = estimate_tokens(segment)

        # If adding this segment exceeds max, finalise current chunk
        if current_tokens + seg_tokens > max_tokens and current_parts:
            chunk_text = "\n\n".join(current_parts)
            chunks.append(DocumentChunk(
                content=chunk_text,
                chunk_index=len(chunks),
                token_count=estimate_tokens(chunk_text),
            ))

            # Carry over last part for overlap
            overlap_tokens = int(current_tokens * overlap_ratio)
            overlap_parts = []
            overlap_count = 0
            for part in reversed(current_parts):
                part_tokens = estimate_tokens(part)
                if overlap_count + part_tokens > overlap_tokens:
                    break
                overlap_parts.insert(0, part)
                overlap_count += part_tokens

            current_parts = overlap_parts
            current_tokens = overlap_count

        current_parts.append(segment)
        current_tokens += seg_tokens

    # Don't forget the last chunk
    if current_parts:
        chunk_text = "\n\n".join(current_parts)
        if estimate_tokens(chunk_text) >= min_tokens // 2 or not chunks:
            chunks.append(DocumentChunk(
                content=chunk_text,
                chunk_index=len(chunks),
                token_count=estimate_tokens(chunk_text),
            ))
        elif chunks:
            # Merge small trailing content into last chunk
            last = chunks[-1]
            merged = last.content + "\n\n" + chunk_text
            chunks[-1] = DocumentChunk(
                content=merged,
                chunk_index=last.chunk_index,
                token_count=estimate_tokens(merged),
            )

    logger.info(
        "document_chunked",
        total_chars=len(text),
        total_chunks=len(chunks),
        avg_tokens=sum(c.token_count for c in chunks) // max(len(chunks), 1),
    )
    return chunks


def _split_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences."""
    sentences = re.split(r'(?<=[.!?])\s+', text)
    # Merge very short sentences (< 20 chars) with the next one
    merged = []
    buffer = ""
    for s in sentences:
        buffer = f"{buffer} {s}".strip() if buffer else s
        if len(buffer) >= 80:
            merged.append(buffer)
            buffer = ""
    if buffer:
        if merged:
            merged[-1] = f"{merged[-1]} {buffer}"
        else:
            merged.append(buffer)
    return merged
