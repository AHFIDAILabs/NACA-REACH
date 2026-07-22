"""
NACA AI Chatbot — Faithfulness Scorer (Section 3.2.3)

Validates that LLM-generated responses are grounded in the retrieved
knowledge base chunks. Prevents hallucinated medical information from
being dispatched to users.

Uses a lightweight entailment check: compares key claims in the response
against the source chunks. Flags responses that contain information
not found in the retrieved context.
"""

import re

import structlog

from src.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Minimum faithfulness score to pass (0.0 to 1.0)
FAITHFULNESS_THRESHOLD = 0.6

# Medical terms that MUST be grounded in sources (never hallucinated)
CRITICAL_MEDICAL_TERMS = {
    "dosage", "mg", "milligram",
    "contraindicated", "pregnancy category",
    "cd4", "viral load",
    "first-line", "second-line",
    "tenofovir", "lamivudine", "dolutegravir", "efavirenz",
    "emtricitabine", "zidovudine", "nevirapine", "atazanavir",
    "lopinavir", "ritonavir",
}

# Statistical/numerical patterns that must be grounded
NUMERICAL_PATTERN = re.compile(
    r'\b(\d+\.?\d*)\s*(%|percent|mg|ml|hours?|days?|weeks?|months?|years?)\b',
    re.IGNORECASE,
)


class FaithfulnessScorer:
    """
    Checks that an LLM response is faithful to the retrieved source content.

    Scoring approach:
    1. Extract key claims from the response (sentences with facts/numbers)
    2. Check each claim against the source chunks
    3. Flag any claim that contains critical medical terms not in sources
    4. Return overall faithfulness score and flagged issues
    """

    def score(
        self,
        response_text: str,
        source_context: str,
    ) -> dict:
        """
        Score the faithfulness of a response against source context.

        Returns:
            {
                "score": float (0.0 to 1.0),
                "passed": bool,
                "flagged_claims": list[str],
                "medical_terms_ungrounded": list[str],
                "numerical_claims_ungrounded": list[str],
            }
        """
        if not source_context or not source_context.strip():
            # No source context — can't validate faithfulness
            # Allow general conversational responses through
            if self._contains_medical_claims(response_text):
                logger.warning("medical_claims_without_source_context")
                return {
                    "score": 0.3,
                    "passed": False,
                    "flagged_claims": ["Response contains medical claims but no source context was available"],
                    "medical_terms_ungrounded": [],
                    "numerical_claims_ungrounded": [],
                }
            return {
                "score": 1.0,
                "passed": True,
                "flagged_claims": [],
                "medical_terms_ungrounded": [],
                "numerical_claims_ungrounded": [],
            }

        source_lower = source_context.lower()
        response_lower = response_text.lower()

        # Check 1: Critical medical terms in response must be in source
        ungrounded_medical = []
        for term in CRITICAL_MEDICAL_TERMS:
            if term in response_lower and term not in source_lower:
                ungrounded_medical.append(term)

        # Check 2: Numerical/statistical claims must be in source
        ungrounded_numbers = []
        response_numbers = NUMERICAL_PATTERN.findall(response_text)
        for number, unit in response_numbers:
            claim = f"{number} {unit}".lower()
            # Check if this exact number+unit appears in source
            if number not in source_lower:
                ungrounded_numbers.append(f"{number} {unit}")

        # Check 3: Sentence-level claim grounding
        sentences = self._split_sentences(response_text)
        flagged = []
        grounded_count = 0
        factual_count = 0

        for sentence in sentences:
            if self._is_grounded(sentence, source_context):
                grounded_count += 1
            elif self._contains_factual_claim(sentence):
                flagged.append(sentence)
                factual_count += 1
            else:
                # Non-factual sentence (conversational) — counts as grounded
                grounded_count += 1

        # Calculate score
        total_checkable = len(sentences) if sentences else 1
        base_score = grounded_count / total_checkable

        # Penalise for ungrounded medical terms (serious)
        medical_penalty = len(ungrounded_medical) * 0.15
        number_penalty = len(ungrounded_numbers) * 0.05
        final_score = max(0.0, min(1.0, base_score - medical_penalty - number_penalty))

        passed = (
            final_score >= FAITHFULNESS_THRESHOLD
            and len(ungrounded_medical) == 0
        )

        if not passed:
            logger.warning(
                "faithfulness_check_failed",
                score=round(final_score, 3),
                ungrounded_medical=ungrounded_medical,
                ungrounded_numbers=ungrounded_numbers,
                flagged_claims=len(flagged),
            )

        return {
            "score": round(final_score, 3),
            "passed": passed,
            "flagged_claims": flagged[:5],  # Limit to top 5
            "medical_terms_ungrounded": ungrounded_medical,
            "numerical_claims_ungrounded": ungrounded_numbers,
        }

    def validate_and_sanitise(
        self, response_text: str, source_context: str
    ) -> tuple[str, dict]:
        """
        Score faithfulness and sanitise the response if needed.

        If faithfulness fails:
        - For mild failures: add a disclaimer
        - For severe failures (ungrounded medical terms): replace with safe fallback

        Returns: (sanitised_text, score_details)
        """
        result = self.score(response_text, source_context)

        if result["passed"]:
            return response_text, result

        # Severe: ungrounded medical terms — cannot send this response
        if result["medical_terms_ungrounded"]:
            safe_response = (
                "I want to make sure I give you accurate information. "
                "I couldn't find specific details about that in my knowledge base. "
                "For the most accurate guidance, I recommend speaking with a healthcare "
                "provider or contacting a nearby HIV service facility. "
                "Would you like me to help you find one?"
            )
            logger.warning(
                "response_replaced_due_to_hallucination",
                original_length=len(response_text),
                ungrounded_terms=result["medical_terms_ungrounded"],
            )
            return safe_response, result

        # Mild: add disclaimer
        disclaimer = (
            "\n\n⚠️ Please note: Some details in this response may not be fully "
            "verified. For important health decisions, please consult a healthcare provider."
        )
        return response_text + disclaimer, result

    def _is_grounded(self, sentence: str, source: str) -> bool:
        """Check if a sentence's key terms appear in the source context."""
        words = set(re.findall(r'[a-z]{3,}', sentence.lower()))
        source_words = set(re.findall(r'[a-z]{3,}', source.lower()))

        # Remove common stop words
        stop = {"the", "and", "for", "are", "but", "not", "you", "all",
                "can", "had", "her", "was", "one", "our", "out", "has",
                "this", "that", "with", "have", "from", "they", "been",
                "will", "your", "what", "when", "make", "like", "just",
                "also", "more", "some", "than", "them", "very", "about"}
        content_words = words - stop

        if not content_words:
            return True  # No substantive content to check

        overlap = content_words & source_words
        return len(overlap) / len(content_words) >= 0.4

    def _contains_factual_claim(self, sentence: str) -> bool:
        """Check if a sentence contains a factual claim (not just conversational)."""
        factual_indicators = [
            r'\d+',  # Contains numbers
            r'\b(study|research|evidence|according|recommended|guideline)\b',
            r'\b(effective|efficacy|rate|percent|risk|cause|prevent)\b',
        ]
        sentence_lower = sentence.lower()
        return any(re.search(p, sentence_lower) for p in factual_indicators)

    def _contains_medical_claims(self, text: str) -> bool:
        """Check if text contains medical/clinical claims."""
        text_lower = text.lower()
        return any(term in text_lower for term in CRITICAL_MEDICAL_TERMS)

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences if len(s.strip()) > 15]
