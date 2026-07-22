"""
NACA AI Chatbot — Agentic RAG Tool Registry & Reasoning Loop
(Section 3.2.0, 3.2.0a, 3.2.0b)

The LLM acts as a reasoning agent that autonomously plans which tools
to invoke, evaluates retrieved information quality, and performs
multi-step retrieval before generating a final response.

Agent Tools:
- KnowledgeSearch: Hybrid vector + BM25 search across knowledge base
- FacilityLookup:  Geospatial facility search
- DrugInfoLookup:  Structured drug information retrieval
- MythChecker:     Myth-busting corpus search
- CrisisDetector:  Proactive crisis signal evaluation
"""

from dataclasses import dataclass, field
from typing import Any
import time

import structlog

from src.core.config import get_settings
from src.schemas.messages import (
    IntentCategory,
    SessionState,
    RetrievedChunk,
    SupportedLanguage,
)
from src.services.rag.retriever import RAGRetriever
from src.services.rag.bm25_index import BM25Index, get_bm25_index

logger = structlog.get_logger()
settings = get_settings()

MAX_RETRIES_PER_TOOL = 3
MIN_CONFIDENCE_THRESHOLD = 0.5


@dataclass
class ToolResult:
    """Result from an agent tool invocation."""
    tool_name: str
    success: bool
    content: str
    confidence: float = 0.0
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentPlan:
    """Plan of tools the agent decides to invoke for a query."""
    tools: list[str]
    parallel: bool = False  # Whether tools can run in parallel
    reasoning: str = ""


class AgentToolRegistry:
    """
    Registry of specialised tools available to the Agentic RAG agent.
    Each tool handles a specific knowledge domain or capability.
    """

    def __init__(self, db=None):
        self.retriever = RAGRetriever()
        self.db = db
        self._tools = {
            "KnowledgeSearch": self._knowledge_search,
            "FacilityLookup": self._facility_lookup,
            "DrugInfoLookup": self._drug_info_lookup,
            "MythChecker": self._myth_checker,
            "CrisisDetector": self._crisis_detector,
        }

    def available_tools(self) -> list[str]:
        return list(self._tools.keys())

    # ── Tool: KnowledgeSearch ────────────────────────────────────────────

    async def _knowledge_search(
        self, query: str, domain: str | None = None, **kwargs
    ) -> ToolResult:
        """
        Hybrid vector + BM25 search across the HIV knowledge base.
        Combines dense semantic search with sparse keyword matching.
        """
        # Dense vector search
        vector_result = await self.retriever.retrieve(
            query=query,
            content_domain=domain,
            top_k=settings.retrieval_top_k,
        )

        # Sparse BM25 search
        bm25_index = get_bm25_index()
        bm25_results = bm25_index.search(
            query=query,
            top_k=settings.retrieval_top_k,
            domain_filter=domain,
        )

        # Merge and deduplicate results (reciprocal rank fusion)
        merged = self._reciprocal_rank_fusion(
            vector_chunks=vector_result.chunks,
            bm25_results=bm25_results,
            top_k=settings.retrieval_top_k,
        )

        if not merged:
            return ToolResult(
                tool_name="KnowledgeSearch",
                success=False,
                content="No relevant knowledge found for this query.",
                confidence=0.0,
            )

        # Format retrieved content for LLM context
        context_parts = []
        for chunk in merged:
            source = chunk.get("source_title", "Unknown")
            context_parts.append(
                f"[Source: {source}]\n{chunk['content']}"
            )

        content = "\n\n---\n\n".join(context_parts)
        avg_conf = sum(c.get("score", 0) for c in merged) / len(merged)

        return ToolResult(
            tool_name="KnowledgeSearch",
            success=True,
            content=content,
            confidence=avg_conf,
            metadata={"chunks_used": len(merged), "method": "hybrid"},
        )

    # ── Tool: FacilityLookup ─────────────────────────────────────────────

    async def _facility_lookup(
        self, query: str, latitude: float | None = None,
        longitude: float | None = None, service_type: str | None = None,
        **kwargs
    ) -> ToolResult:
        """
        Geospatial facility search. Accepts coordinates or text location.
        """
        if not self.db:
            return ToolResult(
                tool_name="FacilityLookup",
                success=False,
                content="Facility search unavailable (no database connection).",
                confidence=0.0,
            )

        from src.services.referral.facility_service import FacilityService
        service = FacilityService(self.db)

        # Extract location from query text if coordinates not provided
        text_location = None
        if not latitude or not longitude:
            text_location = self._extract_location_from_query(query)

        result = await service.find_nearest(
            latitude=latitude,
            longitude=longitude,
            text_location=text_location,
            service_type=service_type,
            radius_km=settings.referral_default_radius_km,
            limit=3,
        )

        if not result.facilities:
            return ToolResult(
                tool_name="FacilityLookup",
                success=False,
                content="No facilities found near the specified location.",
                confidence=0.3,
            )

        # Format facility cards
        cards = []
        for f in result.facilities:
            cards.append(
                f"📍 {f.facility_name}\n"
                f"   Address: {f.address}\n"
                f"   Phone: {f.phone_primary}\n"
                f"   Services: {', '.join(f.services)}\n"
                f"   Hours: {f.operating_hours}\n"
                f"   Distance: {f.distance_km:.1f} km"
            )

        return ToolResult(
            tool_name="FacilityLookup",
            success=True,
            content="\n\n".join(cards),
            confidence=0.9,
            metadata={"facilities_found": len(result.facilities)},
        )

    # ── Tool: DrugInfoLookup ─────────────────────────────────────────────

    async def _drug_info_lookup(self, query: str, **kwargs) -> ToolResult:
        """
        Structured drug information retrieval.
        Searches the knowledge base filtered to ART_TREATMENT domain.
        """
        result = await self.retriever.retrieve(
            query=query,
            content_domain="ART_TREATMENT",
            top_k=3,
        )

        if not result.chunks or result.average_confidence < MIN_CONFIDENCE_THRESHOLD:
            return ToolResult(
                tool_name="DrugInfoLookup",
                success=False,
                content="No specific drug information found. Please consult a healthcare provider.",
                confidence=result.average_confidence,
            )

        content = "\n\n".join(
            f"[{c.source_title}]\n{c.content}" for c in result.chunks
        )

        return ToolResult(
            tool_name="DrugInfoLookup",
            success=True,
            content=content,
            confidence=result.average_confidence,
        )

    # ── Tool: MythChecker ────────────────────────────────────────────────

    async def _myth_checker(self, query: str, **kwargs) -> ToolResult:
        """
        Myth-busting retrieval. Searches the myth-correction corpus.
        """
        result = await self.retriever.retrieve(
            query=query,
            content_domain="MYTH_CORRECTION",
            top_k=3,
        )

        if not result.chunks:
            # Fall back to general knowledge search for myth-related queries
            result = await self.retriever.retrieve(
                query=f"myth fact HIV {query}",
                top_k=3,
            )

        if not result.chunks:
            return ToolResult(
                tool_name="MythChecker",
                success=False,
                content="No myth-correction content found for this query.",
                confidence=0.0,
            )

        content = "\n\n".join(
            f"[Evidence: {c.source_title}]\n{c.content}" for c in result.chunks
        )

        return ToolResult(
            tool_name="MythChecker",
            success=True,
            content=content,
            confidence=result.average_confidence,
        )

    # ── Tool: CrisisDetector ─────────────────────────────────────────────

    async def _crisis_detector(self, query: str, **kwargs) -> ToolResult:
        """
        Evaluate message for crisis signals.
        Called proactively on every message during agent planning phase.
        Uses the NLU intent classifier's escalation trigger detection.
        """
        from src.services.nlu.intent_classifier import classify_intent

        nlu_result = await classify_intent(query)

        return ToolResult(
            tool_name="CrisisDetector",
            success=True,
            content="" if not nlu_result.requires_escalation else "CRISIS_DETECTED",
            confidence=1.0,
            metadata={
                "requires_escalation": nlu_result.requires_escalation,
                "distress_level": nlu_result.distress_level,
                "trigger_type": nlu_result.escalation_trigger.value if nlu_result.escalation_trigger else None,
                "priority": nlu_result.escalation_priority.value if nlu_result.escalation_priority else None,
            },
        )

    # ── Agent Planning ───────────────────────────────────────────────────

    def plan_tools(self, query: str, intent: IntentCategory) -> AgentPlan:
        """
        Decide which tools to invoke based on query analysis.
        The agent reasons about what knowledge domains are required.

        See Section 3.2.0 — Query Analysis and Tool Planning.
        """
        tools = ["CrisisDetector"]  # Always run crisis detection

        if intent == IntentCategory.REFERRAL:
            tools.extend(["FacilityLookup", "KnowledgeSearch"])
            return AgentPlan(tools=tools, parallel=True,
                             reasoning="Referral query: need facility search + supporting info")

        if intent == IntentCategory.TREATMENT:
            tools.extend(["DrugInfoLookup", "KnowledgeSearch"])
            return AgentPlan(tools=tools, parallel=True,
                             reasoning="Treatment query: need drug info + clinical knowledge")

        if intent == IntentCategory.MYTH_BUSTING:
            tools.extend(["MythChecker", "KnowledgeSearch"])
            return AgentPlan(tools=tools, parallel=True,
                             reasoning="Myth query: need myth-correction + evidence")

        if intent == IntentCategory.PREVENTION:
            tools.append("KnowledgeSearch")
            return AgentPlan(tools=tools,
                             reasoning="Prevention query: knowledge base search")

        if intent == IntentCategory.TESTING:
            tools.extend(["KnowledgeSearch", "FacilityLookup"])
            return AgentPlan(tools=tools, parallel=True,
                             reasoning="Testing query: info + possible facility referral")

        # Default: general knowledge search
        tools.append("KnowledgeSearch")
        return AgentPlan(tools=tools,
                         reasoning="General query: knowledge base search")

    # ── Agent Execution Loop ─────────────────────────────────────────────

    async def execute_plan(
        self, query: str, plan: AgentPlan, session: SessionState | None = None,
        **extra_kwargs,
    ) -> list[ToolResult]:
        """
        Execute the agent's tool plan. Implements the agentic reasoning loop:
        1. Execute each tool
        2. Evaluate confidence of results
        3. Retry with reformulated query if confidence too low (max 3 retries)
        4. Collect all results for synthesis

        See Section 3.2.0b — Agentic Reasoning Loop.
        """
        results = []
        start = time.time()

        for tool_name in plan.tools:
            if tool_name not in self._tools:
                logger.warning("unknown_tool_in_plan", tool=tool_name)
                continue

            tool_fn = self._tools[tool_name]
            result = await self._execute_with_retry(
                tool_fn=tool_fn,
                tool_name=tool_name,
                query=query,
                **extra_kwargs,
            )
            results.append(result)

        elapsed_ms = int((time.time() - start) * 1000)
        logger.info(
            "agent_plan_executed",
            tools=plan.tools,
            results_count=len(results),
            successful=sum(1 for r in results if r.success),
            elapsed_ms=elapsed_ms,
        )

        return results

    async def _execute_with_retry(
        self, tool_fn, tool_name: str, query: str, **kwargs
    ) -> ToolResult:
        """Execute a tool with retry on low confidence (max 3 attempts)."""
        current_query = query

        for attempt in range(1, MAX_RETRIES_PER_TOOL + 1):
            result = await tool_fn(query=current_query, **kwargs)

            if result.success and result.confidence >= MIN_CONFIDENCE_THRESHOLD:
                return result

            if attempt < MAX_RETRIES_PER_TOOL:
                # Reformulate query for retry (broaden the search)
                current_query = self._reformulate_query(query, attempt)
                logger.info(
                    "tool_retry",
                    tool=tool_name,
                    attempt=attempt,
                    confidence=result.confidence,
                    reformulated_query=current_query,
                )

        return result  # Return best effort after max retries

    def _reformulate_query(self, original: str, attempt: int) -> str:
        """Broaden query for retry attempts."""
        if attempt == 1:
            return f"HIV {original}"
        elif attempt == 2:
            # Extract key nouns and search more broadly
            words = original.lower().split()
            key_terms = [w for w in words if len(w) > 3][:5]
            return " ".join(key_terms)
        return original

    def _extract_location_from_query(self, query: str) -> str | None:
        """Extract location mentions from query text."""
        import re
        nigerian_states = [
            "lagos", "kano", "rivers", "abuja", "fct", "oyo", "benue",
            "nasarawa", "kaduna", "ogun", "enugu", "anambra", "delta",
            "edo", "cross river", "akwa ibom", "imo", "abia", "plateau",
            "kwara", "niger", "bauchi", "borno", "adamawa", "taraba",
            "gombe", "yobe", "jigawa", "katsina", "kebbi", "sokoto",
            "zamfara", "ekiti", "ondo", "osun", "ebonyi", "bayelsa",
        ]
        query_lower = query.lower()
        for state in nigerian_states:
            if state in query_lower:
                return state
        return None

    # ── Result Fusion ────────────────────────────────────────────────────

    def _reciprocal_rank_fusion(
        self, vector_chunks: list[RetrievedChunk],
        bm25_results: list, top_k: int = 5, k: int = 60,
    ) -> list[dict]:
        """
        Merge vector and BM25 results using Reciprocal Rank Fusion (RRF).
        RRF score = sum(1 / (k + rank)) across all result lists.
        """
        scores: dict[str, float] = {}
        content_map: dict[str, dict] = {}

        # Score vector results
        for rank, chunk in enumerate(vector_chunks):
            key = chunk.chunk_id
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
            content_map[key] = {
                "content": chunk.content,
                "source_title": chunk.source_title,
                "score": chunk.confidence_score,
                "domain": chunk.content_domain,
            }

        # Score BM25 results
        for rank, result in enumerate(bm25_results):
            key = result.chunk_id
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank + 1)
            if key not in content_map:
                content_map[key] = {
                    "content": result.content,
                    "source_title": result.metadata.get("source_title", "Unknown"),
                    "score": result.score,
                    "domain": result.metadata.get("content_domain", ""),
                }

        # Rank by fused score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]

        return [
            {**content_map[chunk_id], "rrf_score": rrf_score}
            for chunk_id, rrf_score in ranked
            if chunk_id in content_map
        ]


def synthesize_tool_results(results: list[ToolResult]) -> str:
    """
    Combine all tool results into a single context string
    for the LLM to use in response generation.
    """
    parts = []
    for r in results:
        if r.success and r.content and r.tool_name != "CrisisDetector":
            parts.append(
                f"## Information from {r.tool_name} "
                f"(confidence: {r.confidence:.0%})\n\n{r.content}"
            )

    return "\n\n---\n\n".join(parts) if parts else ""
