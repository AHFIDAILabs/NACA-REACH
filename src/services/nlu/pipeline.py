"""
NACA AI Chatbot — Unified NLU Pipeline (Section 3.1.1)

Combines all NLU components into a single processing pipeline:
1. Language detection
2. Text normalisation (Pidgin/SMS cleanup)
3. Intent classification + escalation trigger detection
4. Entity extraction (locations, drugs, services, symptoms)
5. Sentiment / distress scoring

This is the single entry point called by the AI Orchestrator.
"""

import structlog

from src.schemas.messages import NLUResult, SupportedLanguage
from src.services.nlu.language_detector import detect_language
from src.services.nlu.text_normaliser import normalise_text
from src.services.nlu.intent_classifier import classify_intent
from src.services.nlu.entity_extractor import extract_entities

logger = structlog.get_logger()


async def process_nlu(
    text: str,
    language_hint: SupportedLanguage | None = None,
) -> NLUResult:
    """
    Full NLU processing pipeline for a user message.

    Args:
        text: Raw user message text
        language_hint: Optional language hint from prior detection

    Returns:
        NLUResult with intent, entities, sentiment, distress, escalation flags
    """
    if not text or not text.strip():
        return NLUResult(
            intent="unknown",
            intent_confidence=0.0,
            sentiment_score=0.0,
            distress_level=0.0,
            detected_language=language_hint or SupportedLanguage.ENGLISH,
        )

    # ── Step 1: Language detection ──
    detected_lang = language_hint or detect_language(text)

    # ── Step 2: Text normalisation ──
    normalised = normalise_text(text, language=detected_lang.value)

    # ── Step 3: Intent classification + escalation detection ──
    # (classify_intent works on English or normalised text)
    nlu_result = await classify_intent(normalised)

    # Override language with our detection
    nlu_result.detected_language = detected_lang

    # ── Step 4: Entity extraction ──
    entities = extract_entities(normalised)
    nlu_result.entities = entities.to_dict()

    # Enrich with first detected service type for referral routing
    if entities.service_types and "service_type" not in nlu_result.entities:
        nlu_result.entities["service_type"] = entities.service_types[0]

    # Enrich with first detected location
    if entities.locations:
        nlu_result.entities["location"] = entities.locations[0]

    logger.info(
        "nlu_pipeline_complete",
        language=detected_lang.value,
        intent=nlu_result.intent.value if hasattr(nlu_result.intent, 'value') else nlu_result.intent,
        confidence=round(nlu_result.intent_confidence, 3),
        entities_count=len(nlu_result.entities),
        distress=nlu_result.distress_level,
        escalation=nlu_result.requires_escalation,
    )

    return nlu_result
