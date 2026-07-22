"""
NLU Processor — Natural Language Understanding Module

Handles intent classification, entity extraction, sentiment analysis,
and distress-level scoring. See: Section 3.1.1

In the initial build, this uses keyword/pattern-based classification.
Phase 2 will replace with fine-tuned ML models trained on annotated data.
"""

import re
from typing import Optional

import structlog

from src.schemas.messages import (
    ConversationTurn,
    EscalationPriority,
    EscalationTriggerType,
    IntentCategory,
    NLUResult,
    SupportedLanguage,
)

logger = structlog.get_logger()


# ── Intent keyword patterns ──────────────────────────────────────────────────

INTENT_PATTERNS: dict[IntentCategory, list[str]] = {
    IntentCategory.GREETING: [
        r"(?i)^(hi|hello|hey|good\s*(morning|afternoon|evening)|howdy|greetings)",
        r"(?i)^(how are you|what'?s up|sup\b)",
    ],
    IntentCategory.PREVENTION: [
        r"(?i)(prevent|prevention|protect|condom|safe\s*sex|PrEP|pre.?exposure)",
        r"(?i)(how.*(?:avoid|prevent|protect).*HIV)",
        r"(?i)(risk|risky|unprotect|transmit|transmission|spread)",
    ],
    IntentCategory.TESTING: [
        r"(?i)(test|testing|tested|get\s*tested|where.*test|HIV\s*test)",
        r"(?i)(check.*status|know.*status|VCT|HTS)",
        r"(?i)(window\s*period|result|negative|positive)",
    ],
    IntentCategory.TREATMENT: [
        r"(?i)(ART|ARV|antiretroviral|treatment|medication|medicine|drug)",
        r"(?i)(viral\s*load|CD4|adherence|dose|dosage|side\s*effect)",
        r"(?i)(PEP|post.?exposure|missed.*dose|refill)",
        r"(?i)(living\s*with\s*HIV|PLHIV|newly\s*diagnosed)",
    ],
    IntentCategory.REFERRAL: [
        r"(?i)(nearest|closest|near\s*me|where.*(?:go|find|get)|facility|clinic|hospital|centre|center)",
        r"(?i)(location|direction|address|referral)",
    ],
    IntentCategory.MYTH_BUSTING: [
        r"(?i)(myth|true.*that|is\s*it\s*true|rumor|rumour|heard\s*that|people\s*say)",
        r"(?i)(can\s*you\s*get.*from|cure.*HIV|prayer.*cure|herbal.*cure)",
        r"(?i)(mosquito|toilet\s*seat|sharing\s*food|kissing.*HIV|swimming)",
    ],
    IntentCategory.CRISIS: [
        r"(?i)(suicid|kill\s*my|end\s*my\s*life|want\s*to\s*die|no\s*reason\s*to\s*live)",
        r"(?i)(self.?harm|hurt\s*myself|cutting\s*myself)",
        r"(?i)(rape|assault|abuse|violence|being\s*beaten)",
        r"(?i)(child.*HIV|minor.*positive|underage)",
    ],
    IntentCategory.OPT_OUT: [
        r"(?i)^(stop|unsubscribe|opt.?out|leave|quit|delete\s*my\s*data)$",
    ],
    IntentCategory.ESCALATION_REQUEST: [
        r"(?i)(agent|human|person|speak.*someone|talk.*someone|real\s*person|operator)",
    ],
    IntentCategory.LANGUAGE_CHANGE: [
        r"(?i)(speak|talk|respond|switch).*(hausa|yoruba|igbo|pidgin|english)",
        r"(?i)^(hausa|yoruba|igbo|pidgin)$",
    ],
}

# ── Crisis keywords for distress scoring ─────────────────────────────────────

CRISIS_KEYWORDS_HIGH = [
    "suicide", "suicidal", "kill myself", "end my life", "want to die",
    "self-harm", "cutting", "rape", "assault", "abuse",
]

CRISIS_KEYWORDS_MODERATE = [
    "scared", "afraid", "worried", "anxious", "depressed", "hopeless",
    "alone", "nobody cares", "stigma", "rejected", "ashamed",
    "positive result", "just found out", "diagnosed",
]

# ── Entity extraction patterns ───────────────────────────────────────────────

NIGERIAN_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue",
    "Borno", "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu",
    "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi",
    "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo",
    "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba", "Yobe",
    "Zamfara", "FCT", "Abuja",
]

DRUG_NAMES = [
    "ART", "ARV", "PrEP", "PEP", "Truvada", "Descovy",
    "dolutegravir", "DTG", "tenofovir", "TDF", "TAF",
    "lamivudine", "3TC", "efavirenz", "EFV", "nevirapine", "NVP",
    "lopinavir", "ritonavir", "atazanavir",
]


class NLUProcessor:
    """
    Processes user messages to extract intent, entities, and sentiment.

    Current implementation: Rule-based keyword matching.
    Future: Fine-tuned ML classifiers (Step 07 of build process).
    """

    async def process(
        self,
        text: str,
        conversation_history: Optional[list[ConversationTurn]] = None,
    ) -> NLUResult:
        """Run the full NLU pipeline on a user message."""

        intent, confidence = self._classify_intent(text)
        entities = self._extract_entities(text)
        sentiment, distress = self._analyse_sentiment(text)
        detected_lang = self._detect_language_hint(text)

        # Determine if escalation is needed
        requires_escalation = False
        escalation_trigger = None
        escalation_priority = None

        if intent == IntentCategory.CRISIS:
            requires_escalation = True
            escalation_trigger = EscalationTriggerType.CRISIS_LANGUAGE
            escalation_priority = EscalationPriority.P1_CRITICAL

        elif intent == IntentCategory.ESCALATION_REQUEST:
            requires_escalation = True
            escalation_trigger = EscalationTriggerType.EXPLICIT_REQUEST
            escalation_priority = EscalationPriority.P3_MEDIUM

        elif distress >= 7.0:
            requires_escalation = True
            escalation_trigger = EscalationTriggerType.POSITIVE_DIAGNOSIS_REACTION
            escalation_priority = EscalationPriority.P1_CRITICAL

        # Check for repeated non-resolution (3+ low-confidence exchanges)
        if conversation_history and not requires_escalation:
            if self._check_repeated_non_resolution(conversation_history):
                requires_escalation = True
                escalation_trigger = EscalationTriggerType.REPEATED_NON_RESOLUTION
                escalation_priority = EscalationPriority.P3_MEDIUM

        return NLUResult(
            intent=intent,
            intent_confidence=confidence,
            entities=entities,
            sentiment_score=sentiment,
            distress_level=distress,
            detected_language=detected_lang,
            requires_escalation=requires_escalation,
            escalation_trigger=escalation_trigger,
            escalation_priority=escalation_priority,
        )

    def _classify_intent(self, text: str) -> tuple[IntentCategory, float]:
        """
        Classify user intent using keyword pattern matching.
        Returns (intent, confidence).
        """
        scores: dict[IntentCategory, float] = {}

        for intent, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text):
                    # Multiple matches increase confidence
                    scores[intent] = scores.get(intent, 0) + 0.4

        if not scores:
            return IntentCategory.UNKNOWN, 0.3

        best_intent = max(scores, key=scores.get)
        confidence = min(scores[best_intent], 0.95)
        return best_intent, confidence

    def _extract_entities(self, text: str) -> dict:
        """Extract named entities from the user message."""
        entities = {}

        # Location entities (Nigerian states)
        for state in NIGERIAN_STATES:
            if re.search(rf"\b{re.escape(state)}\b", text, re.IGNORECASE):
                entities.setdefault("locations", []).append(state)

        # Drug name entities
        for drug in DRUG_NAMES:
            if re.search(rf"\b{re.escape(drug)}\b", text, re.IGNORECASE):
                entities.setdefault("drugs", []).append(drug)

        # Service type extraction
        service_map = {
            r"(?i)test": "HTS",
            r"(?i)ART|ARV|treatment": "ART",
            r"(?i)PrEP|pre.?exposure": "PrEP",
            r"(?i)PEP|post.?exposure": "PEP",
            r"(?i)PMTCT|pregnan|mother.?child": "PMTCT",
            r"(?i)circumcis|VMMC": "VMMC",
            r"(?i)counsel": "Counselling",
            r"(?i)\bTB\b|tubercul": "TB",
        }
        for pattern, service in service_map.items():
            if re.search(pattern, text):
                entities["service_type"] = service
                break

        return entities

    def _analyse_sentiment(self, text: str) -> tuple[float, float]:
        """
        Analyse sentiment and distress level.
        Returns (sentiment_score, distress_level).

        sentiment_score: -1.0 (negative) to 1.0 (positive)
        distress_level: 0 (calm) to 10 (extreme distress)
        """
        text_lower = text.lower()
        distress = 0.0

        # High-severity crisis keywords
        for keyword in CRISIS_KEYWORDS_HIGH:
            if keyword in text_lower:
                distress = max(distress, 8.0)

        # Moderate distress keywords
        for keyword in CRISIS_KEYWORDS_MODERATE:
            if keyword in text_lower:
                distress = max(distress, 4.0)

        # Simple sentiment heuristic
        positive_words = ["thank", "thanks", "great", "good", "helpful", "appreciate"]
        negative_words = ["scared", "afraid", "worried", "angry", "frustrated", "confused"]

        pos_count = sum(1 for w in positive_words if w in text_lower)
        neg_count = sum(1 for w in negative_words if w in text_lower)

        if pos_count + neg_count == 0:
            sentiment = 0.0
        else:
            sentiment = (pos_count - neg_count) / (pos_count + neg_count)

        return sentiment, distress

    def _detect_language_hint(self, text: str) -> SupportedLanguage:
        """Basic language detection from common words."""
        text_lower = text.lower()

        # Hausa markers
        if any(w in text_lower for w in ["sannu", "ina", "yaya", "barka", "nagode"]):
            return SupportedLanguage.HAUSA

        # Yoruba markers
        if any(w in text_lower for w in ["bawo", "ẹ kú", "ṣe", "jọwọ", "e kaaro"]):
            return SupportedLanguage.YORUBA

        # Igbo markers
        if any(w in text_lower for w in ["kedu", "nnọọ", "biko", "daalu"]):
            return SupportedLanguage.IGBO

        # Pidgin markers
        if any(w in text_lower for w in ["wetin", "abeg", "oga", "wahala", "na so"]):
            return SupportedLanguage.PIDGIN

        return SupportedLanguage.ENGLISH

    def _check_repeated_non_resolution(
        self, history: list[ConversationTurn]
    ) -> bool:
        """Check if the last 3 user messages indicate frustration."""
        user_messages = [t for t in history if t.role == "user"][-3:]
        if len(user_messages) < 3:
            return False

        frustration_patterns = [
            r"(?i)(don't understand|not helpful|wrong|that's not|already (said|told|asked))",
            r"(?i)(again|repeat|same thing|not what I)",
        ]
        frustrated_count = sum(
            1 for msg in user_messages
            if any(re.search(p, msg.content) for p in frustration_patterns)
        )
        return frustrated_count >= 2
