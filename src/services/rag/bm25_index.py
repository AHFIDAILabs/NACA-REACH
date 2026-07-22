"""
NACA AI Chatbot — BM25 Sparse Index (Section 3.2.3)

In-memory BM25 keyword index for the sparse component of hybrid retrieval.
Combined with dense vector search for improved recall, especially for
exact medical terms, drug names, and Nigerian location names that
embedding models may not handle well.
"""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()

# Common English stop words to exclude from indexing
STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there", "when",
    "where", "why", "how", "all", "each", "every", "both", "few", "more",
    "most", "other", "some", "such", "no", "not", "only", "own", "same",
    "so", "than", "too", "very", "just", "because", "but", "and", "or",
    "if", "while", "about", "up", "its", "it", "this", "that", "these",
    "those", "i", "me", "my", "we", "our", "you", "your", "he", "him",
    "his", "she", "her", "they", "them", "their", "what", "which", "who",
})


@dataclass
class BM25Result:
    chunk_id: str
    score: float
    content: str
    metadata: dict


class BM25Index:
    """
    BM25 (Okapi BM25) index for keyword-based retrieval.

    Built in-memory from knowledge base chunks. Rebuilt when
    the knowledge base is updated.
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.doc_count = 0
        self.avg_doc_len = 0.0
        self.doc_lengths: dict[str, int] = {}
        self.doc_contents: dict[str, str] = {}
        self.doc_metadata: dict[str, dict] = {}
        self.term_freqs: dict[str, dict[str, int]] = {}   # term -> {doc_id: count}
        self.doc_freqs: dict[str, int] = {}                # term -> num docs containing
        self._built = False

    def add_document(self, chunk_id: str, content: str, metadata: dict | None = None):
        """Add a document chunk to the index."""
        tokens = self._tokenize(content)
        self.doc_lengths[chunk_id] = len(tokens)
        self.doc_contents[chunk_id] = content
        self.doc_metadata[chunk_id] = metadata or {}

        term_counts = Counter(tokens)
        for term, count in term_counts.items():
            if term not in self.term_freqs:
                self.term_freqs[term] = {}
                self.doc_freqs[term] = 0
            self.term_freqs[term][chunk_id] = count
            self.doc_freqs[term] += 1

    def build(self):
        """Finalise the index after all documents are added."""
        self.doc_count = len(self.doc_lengths)
        if self.doc_count > 0:
            self.avg_doc_len = sum(self.doc_lengths.values()) / self.doc_count
        self._built = True
        logger.info(
            "bm25_index_built",
            documents=self.doc_count,
            unique_terms=len(self.term_freqs),
        )

    def search(self, query: str, top_k: int = 5, domain_filter: str | None = None) -> list[BM25Result]:
        """
        Search the index using BM25 scoring.
        Optionally filter by content_domain metadata.
        """
        if not self._built:
            logger.warning("bm25_search_on_unbuilt_index")
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores: dict[str, float] = defaultdict(float)

        for term in query_tokens:
            if term not in self.term_freqs:
                continue

            df = self.doc_freqs[term]
            idf = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1.0)

            for doc_id, tf in self.term_freqs[term].items():
                # Apply domain filter
                if domain_filter:
                    doc_domain = self.doc_metadata.get(doc_id, {}).get("content_domain")
                    if doc_domain and doc_domain != domain_filter:
                        continue

                doc_len = self.doc_lengths[doc_id]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * (doc_len / max(self.avg_doc_len, 1))
                )
                scores[doc_id] += idf * (numerator / denominator)

        # Sort by score descending
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        return [
            BM25Result(
                chunk_id=doc_id,
                score=score,
                content=self.doc_contents[doc_id],
                metadata=self.doc_metadata.get(doc_id, {}),
            )
            for doc_id, score in ranked
        ]

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text: lowercase, alphanumeric, remove stop words."""
        tokens = re.findall(r'[a-z0-9]+', text.lower())
        return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]

    @property
    def size(self) -> int:
        return self.doc_count


# Global singleton — rebuilt when knowledge base changes
_bm25_index = BM25Index()


def get_bm25_index() -> BM25Index:
    """Get the current BM25 index singleton."""
    return _bm25_index
