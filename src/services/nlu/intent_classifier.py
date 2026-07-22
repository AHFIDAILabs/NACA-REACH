"""
NACA AI Chatbot — Intent Classifier & Escalation Trigger Detector

Classifies user intent from English text and detects escalation triggers.
In production, this will be a fine-tuned model. This is a keyword/pattern-based
implementation sufficient for Phase 1 development and testing.
"""

import re
import structlog

from src.schemas.messages import (
    NLUResult,
    IntentCategory,
    SupportedLanguage,
    EscalationPriority,
    EscalationTriggerType,
)

logger = structlog.get_logger()

# ── Intent patterns (English) ────────────────────────────────────────────────
# Each intent has a list of keyword patterns. Matched against lowercased text.

_INTENT_PATTERNS: dict[IntentCategory, list[str]] = {
    IntentCategory.GREETING: [
        r"\b(hello|hi|hey|good morning|good afternoon|good evening|howdy)\b",
        r"^(hi|hey|hello)\s*$",
        r"\b(start|begin|menu)\b",
    ],
    IntentCategory.PREVENTION: [
        r"\b(prevent|prevention|condom|protect|safe sex|abstinence)\b",
        r"\b(prep|pre-exposure|pre exposure|prophylaxis)\b",
        r"\b(pep|post-exposure|post exposure)\b",
        r"\b(pmtct|mother.to.child|pregnant|pregnancy|breastfeed)\b",
        r"\b(circumcision|vmmc)\b",
        r"\b(transmission|transmit|spread|catch|contract)\b",
        r"\b(risk|risky|unprotected)\b",
    ],
    IntentCategory.TESTING: [
        r"\b(test|testing|tested|hts|vct|check|diagnos)\b",
        r"\b(hiv test|get tested|where.*(test|check))\b",
        r"\b(result|positive|negative|status)\b",
        r"\b(window period|rapid test|self.test)\b",
    ],
    IntentCategory.TREATMENT: [
        r"\b(treatment|treat|art\b|arv|antiretroviral)\b",
        r"\b(medication|medicine|drug|dose|dosage)\b",
        r"\b(viral load|cd4|adherence|comply|compliance)\b",
        r"\b(side effect|reaction|interact)\b",
        r"\b(missed.*dose|skip.*dose|forgot.*medication)\b",
        r"\b(refill|pharmacy|clinic|hospital)\b",
    ],
    IntentCategory.REFERRAL: [
        r"\b(where|find|near|nearest|close|closest|locate|location)\b",
        r"\b(facility|centre|center|clinic|hospital)\b",
        r"\b(refer|referral|direct me|point me)\b",
        r"\b(address|direction|map)\b",
    ],
    IntentCategory.MYTH_BUSTING: [
        r"\b(myth|true|false|fact|lie|real|really|misconception)\b",
        r"\b(cure|heal|herbal|traditional|spiritual|pastor|prayer)\b",
        r"\b(mosquito|toilet|kiss|sharing food|swimming)\b",
        r"\b(is it true|can you get|does hiv)\b",
    ],
    IntentCategory.LANGUAGE_CHANGE: [
        r"\b(language|hausa|yoruba|igbo|pidgin|english)\b",
        r"\b(change language|speak|talk in)\b",
    ],
    IntentCategory.OPT_OUT: [
        r"\b(stop|unsubscribe|opt.out|leave|quit|exit|bye|goodbye)\b",
        r"\bdelete my data\b",
    ],
    IntentCategory.ESCALATION_REQUEST: [
        r"\b(agent|human|person|someone|talk to|speak to|real person)\b",
        r"\b(help me|i need help|operator|counsellor|counselor)\b",
    ],
}

# ── Crisis / Escalation trigger patterns (Section 3.5.1) ────────────────────

_CRISIS_PATTERNS = [
    r"\b(suicid|kill myself|end my life|want to die|don't want to live)\b",
    r"\b(self.harm|hurt myself|cutting|harm myself)\b",
    r"\b(abuse|abused|rape|raped|assault|violence|beaten)\b",
    r"\b(hopeless|worthless|no point|give up|can't go on)\b",
]

_DISTRESS_PATTERNS = [
    r"\b(scared|afraid|terrified|anxious|panic|worried|devastat)\b",
    r"\b(depressed|depression|sad|cry|crying|breakdown)\b",
    r"\b(angry|furious|upset|confused|lost|alone|lonely)\b",
    r"\b(diagnosed|just found out|positive result|tested positive)\b",
    r"\b(stigma|discriminat|reject|abandon|ashamed|shame)\b",
]

_SAFEGUARDING_PATTERNS = [
    r"\b(child|minor|underage|young girl|young boy|teenager)\b.*\b(hiv|sex|abuse|expose)\b",
    r"\b(gender.based violence|gbv|domestic violence)\b",
    r"\bforced\b.*\b(sex|marriage|intercourse)\b",
]

_CLINICAL_COMPLEXITY_PATTERNS = [
    r"\b(drug interaction|switch.*regimen|change.*medication)\b",
    r"\b(pregnant.*hiv|hiv.*pregnant)\b",
    r"\b(co.infect|hepatitis|tb.*hiv|hiv.*tb)\b",
    r"\b(treatment failure|resistance|virologic failure)\b",
    r"\b(opportunistic infection)\b",
]


async def classify_intent(text: str) -> NLUResult:
    """
    Classify the intent of a user message and detect escalation triggers.

    Returns NLUResult with intent, confidence, sentiment, distress level,
    and escalation flags.
    """
    text_lower = text.lower().strip()

    # ── 1. Check escalation triggers FIRST (safety priority) ──
    escalation = _check_escalation_triggers(text_lower)
    if escalation:
        return escalation

    # ── 2. Intent classification via pattern matching ──
    intent_scores: dict[IntentCategory, float] = {}

    for intent, patterns in _INTENT_PATTERNS.items():
        match_count = 0
        for pattern in patterns:
            if re.search(pattern, text_lower):
                match_count += 1
        if match_count > 0:
            # Confidence based on number of matching patterns
            intent_scores[intent] = min(0.5 + (match_count * 0.15), 0.95)

    # Select best intent
    if intent_scores:
        best_intent = max(intent_scores, key=intent_scores.get)
        confidence = intent_scores[best_intent]
    else:
        best_intent = IntentCategory.GENERAL_ENQUIRY
        confidence = 0.3

    # ── 3. Sentiment / distress scoring ──
    distress_level = _calculate_distress(text_lower)
    sentiment = _calculate_sentiment(text_lower)

    # If high distress detected even without explicit crisis language, flag it
    if distress_level >= 7.0:
        return NLUResult(
            intent=best_intent,
            intent_confidence=confidence,
            sentiment_score=sentiment,
            distress_level=distress_level,
            detected_language=SupportedLanguage.ENGLISH,
            requires_escalation=True,
            escalation_trigger=EscalationTriggerType.CRISIS_LANGUAGE,
            escalation_priority=EscalationPriority.P1_CRITICAL,
        )

    # Explicit request for human agent — always escalate
    if best_intent == IntentCategory.ESCALATION_REQUEST:
        return NLUResult(
            intent=best_intent,
            intent_confidence=confidence,
            sentiment_score=sentiment,
            distress_level=distress_level,
            detected_language=SupportedLanguage.ENGLISH,
            requires_escalation=True,
            escalation_trigger=EscalationTriggerType.EXPLICIT_REQUEST,
            escalation_priority=EscalationPriority.P3_MEDIUM,
        )

    return NLUResult(
        intent=best_intent,
        intent_confidence=confidence,
        sentiment_score=sentiment,
        distress_level=distress_level,
        detected_language=SupportedLanguage.ENGLISH,
        requires_escalation=False,
    )


def _check_escalation_triggers(text: str) -> NLUResult | None:
    """Check for crisis, safeguarding, and clinical escalation triggers."""

    # P1 — Safeguarding concerns (check FIRST — child safety takes priority)
    for pattern in _SAFEGUARDING_PATTERNS:
        if re.search(pattern, text):
            logger.warning("escalation_safeguarding_detected")
            return NLUResult(
                intent=IntentCategory.CRISIS,
                intent_confidence=0.90,
                sentiment_score=-0.7,
                distress_level=8.0,
                detected_language=SupportedLanguage.ENGLISH,
                requires_escalation=True,
                escalation_trigger=EscalationTriggerType.SAFEGUARDING_CONCERN,
                escalation_priority=EscalationPriority.P1_CRITICAL,
            )

    # P1 — Crisis language
    for pattern in _CRISIS_PATTERNS:
        if re.search(pattern, text):
            logger.warning("escalation_crisis_detected", pattern=pattern)
            return NLUResult(
                intent=IntentCategory.CRISIS,
                intent_confidence=0.95,
                sentiment_score=-0.9,
                distress_level=9.0,
                detected_language=SupportedLanguage.ENGLISH,
                requires_escalation=True,
                escalation_trigger=EscalationTriggerType.CRISIS_LANGUAGE,
                escalation_priority=EscalationPriority.P1_CRITICAL,
            )

    # P2 — Clinical complexity requiring human judgement
    for pattern in _CLINICAL_COMPLEXITY_PATTERNS:
        if re.search(pattern, text):
            logger.info("escalation_clinical_complexity")
            return NLUResult(
                intent=IntentCategory.TREATMENT,
                intent_confidence=0.85,
                sentiment_score=0.0,
                distress_level=3.0,
                detected_language=SupportedLanguage.ENGLISH,
                requires_escalation=True,
                escalation_trigger=EscalationTriggerType.CLINICAL_DECISION_REQUIRED,
                escalation_priority=EscalationPriority.P2_HIGH,
            )

    # P1 — Positive diagnosis emotional reaction
    positive_diagnosis = re.search(
        r"\b(just (found out|tested|got)|recently diagnosed|i am positive|i have hiv)\b",
        text,
    )
    distress_in_diagnosis = any(
        re.search(p, text) for p in _DISTRESS_PATTERNS
    )
    if positive_diagnosis and distress_in_diagnosis:
        logger.warning("escalation_positive_diagnosis_distress")
        return NLUResult(
            intent=IntentCategory.CRISIS,
            intent_confidence=0.90,
            sentiment_score=-0.8,
            distress_level=8.0,
            detected_language=SupportedLanguage.ENGLISH,
            requires_escalation=True,
            escalation_trigger=EscalationTriggerType.POSITIVE_DIAGNOSIS_REACTION,
            escalation_priority=EscalationPriority.P1_CRITICAL,
        )

    return None


def _calculate_distress(text: str) -> float:
    """Score distress level from 0 (calm) to 10 (extreme distress)."""
    score = 0.0
    for pattern in _DISTRESS_PATTERNS:
        if re.search(pattern, text):
            score += 2.0
    for pattern in _CRISIS_PATTERNS:
        if re.search(pattern, text):
            score += 3.0
    return min(score, 10.0)


def _calculate_sentiment(text: str) -> float:
    """Simple sentiment score from -1.0 (very negative) to 1.0 (very positive)."""
    positive_words = {"thank", "thanks", "good", "great", "helpful", "appreciate", "happy"}
    negative_words = {"bad", "terrible", "awful", "angry", "sad", "scared", "worried", "confused"}

    words = set(re.findall(r'\w+', text.lower()))
    pos = len(words & positive_words)
    neg = len(words & negative_words)
    total = pos + neg

    if total == 0:
        return 0.0
    return round((pos - neg) / total, 2)