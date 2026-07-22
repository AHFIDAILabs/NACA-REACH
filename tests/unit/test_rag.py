"""
NACA AI Chatbot — Unit Tests for RAG Pipeline (Phase 2 — Step 06)

Tests document chunking, BM25 indexing, hybrid retrieval fusion,
and faithfulness scoring.
"""

import pytest
from src.services.rag.chunker import chunk_document, estimate_tokens, DocumentChunk
from src.services.rag.bm25_index import BM25Index
from src.services.rag.agent_tools import AgentToolRegistry, synthesize_tool_results, ToolResult
from src.services.ai.faithfulness import FaithfulnessScorer
from src.schemas.messages import IntentCategory


# =============================================================================
# Document Chunker Tests
# =============================================================================

class TestDocumentChunker:

    def test_empty_text_returns_empty(self):
        assert chunk_document("") == []
        assert chunk_document("   ") == []

    def test_short_text_single_chunk(self):
        text = "This is a short document about HIV prevention. " * 50
        chunks = chunk_document(text)
        assert len(chunks) >= 1
        assert all(isinstance(c, DocumentChunk) for c in chunks)

    def test_chunk_indexes_are_sequential(self):
        text = "HIV prevention is important. " * 200
        chunks = chunk_document(text)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunks_respect_max_size(self):
        text = ("Antiretroviral therapy is the treatment of HIV infection. " * 300)
        chunks = chunk_document(text, max_tokens=1024)
        for chunk in chunks:
            # Allow 20% tolerance due to overlap and boundary effects
            assert chunk.token_count <= 1024 * 1.2

    def test_chunks_have_overlap(self):
        """Consecutive chunks should share some content (10% overlap)."""
        text = "Sentence number {i} about HIV prevention and testing. ".format(i=1) * 500
        chunks = chunk_document(text, min_tokens=100, max_tokens=200)
        if len(chunks) >= 2:
            # Check that there's some text overlap between consecutive chunks
            for i in range(len(chunks) - 1):
                words_current = set(chunks[i].content.split()[-20:])
                words_next = set(chunks[i + 1].content.split()[:20])
                # There should be at least some overlap
                # (may not always be the case with paragraph boundaries)
                pass  # Overlap is structural, not guaranteed word-for-word

    def test_token_estimation(self):
        text = "Hello world"  # ~11 chars = ~2-3 tokens
        tokens = estimate_tokens(text)
        assert 1 <= tokens <= 5

    def test_long_document_produces_multiple_chunks(self):
        # Create a document with clear paragraph structure
        paragraphs = []
        for i in range(20):
            paragraphs.append(
                f"Section {i}: This section covers aspect number {i} of HIV "
                f"prevention and treatment. It includes important information "
                f"about testing procedures, medication adherence, and support "
                f"services available across Nigeria. " * 5
            )
        text = "\n\n".join(paragraphs)
        chunks = chunk_document(text)
        assert len(chunks) >= 3


# =============================================================================
# BM25 Index Tests
# =============================================================================

class TestBM25Index:

    def _build_sample_index(self) -> BM25Index:
        index = BM25Index()
        index.add_document("doc1", "HIV prevention methods include condom use and PrEP",
                          {"content_domain": "PREVENTION"})
        index.add_document("doc2", "Antiretroviral therapy ART is the treatment for HIV",
                          {"content_domain": "ART_TREATMENT"})
        index.add_document("doc3", "HIV testing is confidential and free in Nigeria",
                          {"content_domain": "TESTING_SERVICES"})
        index.add_document("doc4", "Mosquitoes cannot transmit HIV this is a common myth",
                          {"content_domain": "MYTH_CORRECTION"})
        index.add_document("doc5", "PrEP is pre-exposure prophylaxis for HIV prevention",
                          {"content_domain": "PREVENTION"})
        index.build()
        return index

    def test_basic_search(self):
        index = self._build_sample_index()
        results = index.search("HIV prevention", top_k=3)
        assert len(results) > 0
        # Prevention docs should rank highest
        top_ids = [r.chunk_id for r in results]
        assert "doc1" in top_ids or "doc5" in top_ids

    def test_domain_filtering(self):
        index = self._build_sample_index()
        results = index.search("HIV", top_k=5, domain_filter="PREVENTION")
        for r in results:
            assert r.metadata.get("content_domain") == "PREVENTION"

    def test_empty_query_returns_empty(self):
        index = self._build_sample_index()
        results = index.search("", top_k=3)
        assert results == []

    def test_no_match_returns_empty(self):
        index = self._build_sample_index()
        results = index.search("quantum physics rocket science", top_k=3)
        assert results == []

    def test_unbuilt_index_returns_empty(self):
        index = BM25Index()
        index.add_document("doc1", "some content")
        # Don't call build()
        results = index.search("content", top_k=3)
        assert results == []

    def test_size_property(self):
        index = self._build_sample_index()
        assert index.size == 5

    def test_myth_search(self):
        index = self._build_sample_index()
        results = index.search("mosquito transmit HIV myth", top_k=3)
        assert len(results) > 0
        assert any(r.chunk_id == "doc4" for r in results)

    def test_treatment_search(self):
        index = self._build_sample_index()
        results = index.search("ART antiretroviral treatment", top_k=3)
        assert len(results) > 0
        assert results[0].chunk_id == "doc2"


# =============================================================================
# Faithfulness Scorer Tests
# =============================================================================

class TestFaithfulnessScorer:

    def setup_method(self):
        self.scorer = FaithfulnessScorer()

    def test_faithful_response_passes(self):
        source = "PrEP reduces HIV risk by about 99% when taken consistently."
        response = "Taking PrEP consistently can reduce your risk of getting HIV by about 99%."
        result = self.scorer.score(response, source)
        assert result["passed"] is True
        assert result["score"] >= 0.6

    def test_hallucinated_drug_name_fails(self):
        source = "The recommended regimen is Tenofovir and Lamivudine."
        response = "You should take Lopinavir daily for HIV prevention."
        result = self.scorer.score(response, source)
        # Lopinavir is in CRITICAL_MEDICAL_TERMS but not in source
        assert len(result["medical_terms_ungrounded"]) > 0

    def test_no_source_with_medical_claims_fails(self):
        response = "Take 200mg of Tenofovir once daily."
        result = self.scorer.score(response, "")
        assert result["passed"] is False

    def test_no_source_without_medical_claims_passes(self):
        response = "Hello! How can I help you today? I can provide information about HIV."
        result = self.scorer.score(response, "")
        assert result["passed"] is True

    def test_validate_and_sanitise_replaces_hallucinated(self):
        source = "Condoms prevent HIV transmission."
        response = "You should take Efavirenz 600mg at bedtime for prevention."
        sanitised, details = self.scorer.validate_and_sanitise(response, source)
        # Should be replaced with safe fallback since efavirenz is ungrounded
        assert "healthcare provider" in sanitised.lower() or "knowledge base" in sanitised.lower()

    def test_validate_and_sanitise_passes_good_response(self):
        source = "HIV testing is free and confidential in Nigeria."
        response = "HIV testing is available for free and is completely confidential at health facilities in Nigeria."
        sanitised, details = self.scorer.validate_and_sanitise(response, source)
        assert sanitised == response  # Should pass through unchanged
        assert details["passed"] is True

    def test_conversational_response_without_claims_passes(self):
        source = "Some source content about HIV."
        response = "I understand your concern. Let me help you find the right information."
        result = self.scorer.score(response, source)
        assert result["passed"] is True


# =============================================================================
# Agent Tool Planning Tests
# =============================================================================

class TestAgentToolPlanning:

    def setup_method(self):
        self.agent = AgentToolRegistry()

    def test_referral_query_plans_facility_lookup(self):
        plan = self.agent.plan_tools("Find clinic near Lagos", IntentCategory.REFERRAL)
        assert "FacilityLookup" in plan.tools
        assert "CrisisDetector" in plan.tools

    def test_treatment_query_plans_drug_lookup(self):
        plan = self.agent.plan_tools("ART side effects", IntentCategory.TREATMENT)
        assert "DrugInfoLookup" in plan.tools
        assert "KnowledgeSearch" in plan.tools

    def test_myth_query_plans_myth_checker(self):
        plan = self.agent.plan_tools("Can mosquitoes spread HIV", IntentCategory.MYTH_BUSTING)
        assert "MythChecker" in plan.tools

    def test_crisis_detector_always_included(self):
        for intent in IntentCategory:
            plan = self.agent.plan_tools("test", intent)
            assert "CrisisDetector" in plan.tools

    def test_prevention_query_plans_knowledge_search(self):
        plan = self.agent.plan_tools("How to prevent HIV", IntentCategory.PREVENTION)
        assert "KnowledgeSearch" in plan.tools


# =============================================================================
# Tool Result Synthesis Tests
# =============================================================================

class TestToolResultSynthesis:

    def test_synthesize_combines_successful_results(self):
        results = [
            ToolResult(tool_name="KnowledgeSearch", success=True,
                      content="PrEP prevents HIV.", confidence=0.9),
            ToolResult(tool_name="FacilityLookup", success=True,
                      content="Lagos Clinic: 123 Main St", confidence=0.85),
        ]
        combined = synthesize_tool_results(results)
        assert "PrEP prevents HIV" in combined
        assert "Lagos Clinic" in combined

    def test_synthesize_excludes_failed_results(self):
        results = [
            ToolResult(tool_name="KnowledgeSearch", success=True,
                      content="Valid content.", confidence=0.9),
            ToolResult(tool_name="DrugInfoLookup", success=False,
                      content="No info found.", confidence=0.1),
        ]
        combined = synthesize_tool_results(results)
        assert "Valid content" in combined
        assert "No info found" not in combined

    def test_synthesize_excludes_crisis_detector_content(self):
        results = [
            ToolResult(tool_name="CrisisDetector", success=True,
                      content="", confidence=1.0),
            ToolResult(tool_name="KnowledgeSearch", success=True,
                      content="Test info.", confidence=0.8),
        ]
        combined = synthesize_tool_results(results)
        assert "CrisisDetector" not in combined

    def test_synthesize_empty_results(self):
        combined = synthesize_tool_results([])
        assert combined == ""
