"""
NACA AI Chatbot — Unit Tests for NLU Services

Tests intent classification, language detection, and escalation trigger detection.
"""

import pytest
from src.services.nlu.language_detector import detect_language
from src.services.nlu.intent_classifier import classify_intent
from src.schemas.messages import (
    SupportedLanguage,
    IntentCategory,
    EscalationPriority,
    EscalationTriggerType,
)


# =============================================================================
# Language Detection Tests
# =============================================================================

class TestLanguageDetector:
    def test_english_default(self):
        assert detect_language("Hello, how are you?") == SupportedLanguage.ENGLISH

    def test_english_hiv_query(self):
        assert detect_language("Where can I get an HIV test?") == SupportedLanguage.ENGLISH

    def test_hausa_detection(self):
        result = detect_language("Ina so in gwajin kanjamau")
        assert result == SupportedLanguage.HAUSA

    def test_yoruba_detection(self):
        result = detect_language("Jọwọ ile-iwosan nibo ni mo le lọ")
        assert result == SupportedLanguage.YORUBA

    def test_pidgin_detection(self):
        result = detect_language("Abeg wetin dey happen for dis test")
        assert result == SupportedLanguage.PIDGIN

    def test_igbo_detection(self):
        result = detect_language("Biko kedu ebe m nwere ike ịga nlele")
        assert result == SupportedLanguage.IGBO

    def test_empty_text_defaults_english(self):
        assert detect_language("") == SupportedLanguage.ENGLISH

    def test_short_text_defaults_english(self):
        assert detect_language("hi") == SupportedLanguage.ENGLISH


# =============================================================================
# Intent Classification Tests
# =============================================================================

class TestIntentClassifier:

    @pytest.mark.asyncio
    async def test_greeting_intent(self):
        result = await classify_intent("Hello, good morning")
        assert result.intent == IntentCategory.GREETING
        assert result.requires_escalation is False

    @pytest.mark.asyncio
    async def test_prevention_intent(self):
        result = await classify_intent("How can I prevent HIV transmission?")
        assert result.intent == IntentCategory.PREVENTION

    @pytest.mark.asyncio
    async def test_testing_intent(self):
        result = await classify_intent("Where can I get an HIV test near me?")
        assert result.intent == IntentCategory.TESTING

    @pytest.mark.asyncio
    async def test_treatment_intent(self):
        result = await classify_intent("What is ART medication and what are the side effects?")
        assert result.intent == IntentCategory.TREATMENT

    @pytest.mark.asyncio
    async def test_referral_intent(self):
        result = await classify_intent("Find the nearest clinic to me in Lagos")
        assert result.intent == IntentCategory.REFERRAL

    @pytest.mark.asyncio
    async def test_myth_busting_intent(self):
        result = await classify_intent("Is it true that mosquitoes can spread HIV?")
        assert result.intent == IntentCategory.MYTH_BUSTING

    @pytest.mark.asyncio
    async def test_opt_out_intent(self):
        result = await classify_intent("Stop sending me messages")
        assert result.intent == IntentCategory.OPT_OUT

    @pytest.mark.asyncio
    async def test_escalation_request_intent(self):
        result = await classify_intent("I want to talk to a human agent")
        assert result.intent == IntentCategory.ESCALATION_REQUEST

    @pytest.mark.asyncio
    async def test_unknown_defaults_general(self):
        result = await classify_intent("asdfghjkl random text")
        assert result.intent == IntentCategory.GENERAL_ENQUIRY
        assert result.intent_confidence < 0.5


# =============================================================================
# Escalation Trigger Tests
# =============================================================================

class TestEscalationTriggers:

    @pytest.mark.asyncio
    async def test_crisis_suicidal_ideation(self):
        result = await classify_intent("I want to kill myself, I can't go on")
        assert result.requires_escalation is True
        assert result.escalation_trigger == EscalationTriggerType.CRISIS_LANGUAGE
        assert result.escalation_priority == EscalationPriority.P1_CRITICAL

    @pytest.mark.asyncio
    async def test_crisis_self_harm(self):
        result = await classify_intent("I've been cutting myself and I want to hurt myself")
        assert result.requires_escalation is True
        assert result.escalation_priority == EscalationPriority.P1_CRITICAL

    @pytest.mark.asyncio
    async def test_safeguarding_child(self):
        result = await classify_intent("My young child was exposed to HIV through abuse")
        assert result.requires_escalation is True
        assert result.escalation_trigger == EscalationTriggerType.SAFEGUARDING_CONCERN
        assert result.escalation_priority == EscalationPriority.P1_CRITICAL

    @pytest.mark.asyncio
    async def test_clinical_complexity_drug_interaction(self):
        result = await classify_intent("Can I switch my ART regimen if I change medication?")
        assert result.requires_escalation is True
        assert result.escalation_trigger == EscalationTriggerType.CLINICAL_DECISION_REQUIRED
        assert result.escalation_priority == EscalationPriority.P2_HIGH

    @pytest.mark.asyncio
    async def test_positive_diagnosis_with_distress(self):
        result = await classify_intent("I just found out I am positive and I am scared and devastated")
        assert result.requires_escalation is True
        assert result.escalation_trigger == EscalationTriggerType.POSITIVE_DIAGNOSIS_REACTION
        assert result.escalation_priority == EscalationPriority.P1_CRITICAL

    @pytest.mark.asyncio
    async def test_normal_message_no_escalation(self):
        result = await classify_intent("What time does the clinic open?")
        assert result.requires_escalation is False

    @pytest.mark.asyncio
    async def test_prevention_query_no_escalation(self):
        result = await classify_intent("How effective are condoms at preventing HIV?")
        assert result.requires_escalation is False


# =============================================================================
# Distress / Sentiment Tests
# =============================================================================

class TestSentiment:

    @pytest.mark.asyncio
    async def test_positive_sentiment(self):
        result = await classify_intent("Thank you so much, that was very helpful!")
        assert result.sentiment_score > 0

    @pytest.mark.asyncio
    async def test_negative_sentiment(self):
        result = await classify_intent("I am scared and confused about my results")
        assert result.sentiment_score < 0

    @pytest.mark.asyncio
    async def test_high_distress_detection(self):
        result = await classify_intent(
            "I am so depressed and scared, I feel alone and hopeless"
        )
        assert result.distress_level >= 4.0
