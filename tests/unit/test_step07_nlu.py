"""
NACA AI Chatbot — Unit Tests for Entity Extraction & Text Normalisation
(Phase 2 — Step 07)
"""

import pytest
from src.services.nlu.entity_extractor import extract_entities
from src.services.nlu.text_normaliser import normalise_text
from src.services.nlu.pipeline import process_nlu
from src.schemas.messages import SupportedLanguage, IntentCategory


# =============================================================================
# Entity Extraction Tests
# =============================================================================

class TestEntityExtractor:

    # ── Location extraction ──

    def test_extract_state(self):
        entities = extract_entities("I live in Lagos and need help")
        assert len(entities.locations) >= 1
        assert any(loc.get("state") == "Lagos" or loc.get("city") == "Lagos" for loc in entities.locations)

    def test_extract_city_with_state(self):
        entities = extract_entities("I am in Ibadan looking for a clinic")
        assert len(entities.locations) >= 1
        loc = entities.locations[0]
        assert loc.get("city") == "Ibadan"
        assert loc.get("state") == "Oyo"

    def test_extract_abuja_fct(self):
        entities = extract_entities("Where can I get tested in Abuja?")
        assert len(entities.locations) >= 1
        assert any("FCT" in str(loc.values()) or "Abuja" in str(loc.values()) for loc in entities.locations)

    def test_extract_multiple_locations(self):
        entities = extract_entities("Clinics in Lagos and Kano")
        assert len(entities.locations) >= 2

    def test_no_location_found(self):
        entities = extract_entities("How can I prevent HIV?")
        assert len(entities.locations) == 0

    # ── Drug extraction ──

    def test_extract_drug_name(self):
        entities = extract_entities("What are the side effects of tenofovir?")
        assert "Tenofovir" in entities.drugs

    def test_extract_drug_abbreviation(self):
        entities = extract_entities("I am taking TDF and 3TC daily")
        assert len(entities.drugs) >= 2

    def test_extract_prep(self):
        entities = extract_entities("Where can I get PrEP?")
        assert any("PrEP" in d or "PREP" in d for d in entities.drugs)

    def test_extract_pep(self):
        entities = extract_entities("I need PEP urgently after exposure")
        assert any("PEP" in d for d in entities.drugs)

    # ── Service type extraction ──

    def test_extract_testing_service(self):
        entities = extract_entities("Where can I get an HIV test?")
        assert "HTS" in entities.service_types

    def test_extract_art_service(self):
        entities = extract_entities("I need antiretroviral treatment")
        assert "ART" in entities.service_types

    def test_extract_pmtct_service(self):
        entities = extract_entities("I am pregnant and HIV positive")
        assert "PMTCT" in entities.service_types

    def test_extract_circumcision(self):
        entities = extract_entities("Where can I get circumcision?")
        assert "VMMC" in entities.service_types

    def test_extract_counselling(self):
        entities = extract_entities("I need mental health counselling")
        assert "Counselling" in entities.service_types

    # ── Symptom extraction ──

    def test_extract_fever(self):
        entities = extract_entities("I have had a fever for 3 days")
        assert any("fever" in s for s in entities.symptoms)

    def test_extract_weight_loss(self):
        entities = extract_entities("I am losing weight rapidly")
        assert any("weight" in s for s in entities.symptoms)

    def test_extract_multiple_symptoms(self):
        entities = extract_entities("I have fever, rash, and fatigue")
        assert len(entities.symptoms) >= 3

    # ── Combined extraction ──

    def test_complex_query_extracts_all(self):
        query = "I need an HIV test in Lagos, I have fever and I take tenofovir"
        entities = extract_entities(query)
        assert len(entities.locations) >= 1
        assert "HTS" in entities.service_types
        assert any("fever" in s for s in entities.symptoms)
        assert "Tenofovir" in entities.drugs

    def test_to_dict(self):
        entities = extract_entities("HIV test in Lagos")
        d = entities.to_dict()
        assert isinstance(d, dict)


# =============================================================================
# Text Normaliser Tests
# =============================================================================

class TestTextNormaliser:

    # ── Pidgin normalisation ──

    def test_pidgin_abeg(self):
        result = normalise_text("abeg whr I fit get test", language="pcm")
        assert "please" in result.lower()

    def test_pidgin_wetin(self):
        result = normalise_text("wetin be HIV?", language="pcm")
        assert "what" in result.lower()

    def test_pidgin_dey(self):
        result = normalise_text("I dey find clinic", language="pcm")
        assert "am" in result.lower() or "is" in result.lower()

    # ── SMS abbreviation expansion ──

    def test_sms_pls(self):
        result = normalise_text("pls help me find a clinic", language="en")
        assert "please" in result.lower()

    def test_sms_u_and_ur(self):
        result = normalise_text("u nd ur family shd get tested", language="en")
        assert "you" in result.lower()
        assert "your" in result.lower()

    def test_sms_b4(self):
        result = normalise_text("take PEP b4 72 hrs", language="en")
        assert "before" in result.lower()

    def test_sms_2moro(self):
        result = normalise_text("I will go 2moro", language="en")
        assert "tomorrow" in result.lower()

    # ── Repeated characters ──

    def test_repeated_chars_cleaned(self):
        result = normalise_text("helpppppp meeeee", language="en")
        assert "pp" in result  # Reduced to max 2 repeats
        assert "ppppp" not in result

    # ── Edge cases ──

    def test_empty_string(self):
        assert normalise_text("", language="en") == ""

    def test_already_clean_text_unchanged(self):
        clean = "Where can I find the nearest HIV testing facility?"
        result = normalise_text(clean, language="en")
        # Should be mostly the same (no abbreviations to expand)
        assert "nearest" in result
        assert "testing" in result

    def test_mixed_pidgin_sms(self):
        result = normalise_text("abeg hlp me, I dey sick", language="pcm")
        assert "please" in result.lower()
        assert "help" in result.lower()


# =============================================================================
# Unified NLU Pipeline Tests
# =============================================================================

class TestNLUPipeline:

    @pytest.mark.asyncio
    async def test_full_pipeline_english(self):
        result = await process_nlu("Where can I get an HIV test in Lagos?")
        assert result.detected_language == SupportedLanguage.ENGLISH
        assert result.intent in (IntentCategory.TESTING, IntentCategory.REFERRAL)
        # Should have extracted location and service type
        assert "locations" in result.entities or "service_types" in result.entities

    @pytest.mark.asyncio
    async def test_full_pipeline_with_entities(self):
        result = await process_nlu(
            "I need PrEP medication at a clinic near Abuja"
        )
        assert "drugs" in result.entities or "service_types" in result.entities

    @pytest.mark.asyncio
    async def test_full_pipeline_pidgin(self):
        result = await process_nlu(
            "abeg wetin be dis HIV ting",
            language_hint=SupportedLanguage.PIDGIN,
        )
        assert result.detected_language == SupportedLanguage.PIDGIN

    @pytest.mark.asyncio
    async def test_full_pipeline_escalation(self):
        result = await process_nlu("I want to kill myself")
        assert result.requires_escalation is True
        assert result.distress_level >= 7.0

    @pytest.mark.asyncio
    async def test_empty_text(self):
        result = await process_nlu("")
        assert result.intent_confidence == 0.0

    @pytest.mark.asyncio
    async def test_language_hint_respected(self):
        result = await process_nlu(
            "Hello",
            language_hint=SupportedLanguage.HAUSA,
        )
        assert result.detected_language == SupportedLanguage.HAUSA
