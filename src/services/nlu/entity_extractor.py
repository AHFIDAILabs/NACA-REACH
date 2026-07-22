"""
NACA AI Chatbot — Entity Extractor (Section 3.1.1)

Named Entity Recognition for:
- Locations: Nigerian states, LGAs, cities, landmarks
- Drug names: ART, PrEP, PEP medications
- Service types: HTS, ART, PrEP, PMTCT, VMMC, etc.
- Symptom descriptors: fever, rash, weight loss, etc.

Uses pattern/dictionary-based extraction. In production, can be
augmented with a fine-tuned NER model.
"""

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()


@dataclass
class ExtractedEntities:
    """All entities extracted from a user message."""
    locations: list[dict] = field(default_factory=list)
    drugs: list[str] = field(default_factory=list)
    service_types: list[str] = field(default_factory=list)
    symptoms: list[str] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = {}
        if self.locations:
            d["locations"] = self.locations
        if self.drugs:
            d["drugs"] = self.drugs
        if self.service_types:
            d["service_types"] = self.service_types
        if self.symptoms:
            d["symptoms"] = self.symptoms
        return d


# ── Nigerian Location Gazetteers ─────────────────────────────────────────────

NIGERIAN_STATES = {
    "abia", "adamawa", "akwa ibom", "anambra", "bauchi", "bayelsa",
    "benue", "borno", "cross river", "delta", "ebonyi", "edo", "ekiti",
    "enugu", "gombe", "imo", "jigawa", "kaduna", "kano", "katsina",
    "kebbi", "kogi", "kwara", "lagos", "nasarawa", "niger", "ogun",
    "ondo", "osun", "oyo", "plateau", "rivers", "sokoto", "taraba",
    "yobe", "zamfara", "fct", "abuja",
}

MAJOR_CITIES = {
    "lagos": "Lagos",
    "abuja": "FCT",
    "kano": "Kano",
    "ibadan": "Oyo",
    "port harcourt": "Rivers",
    "benin city": "Edo",
    "maiduguri": "Borno",
    "zaria": "Kaduna",
    "aba": "Abia",
    "jos": "Plateau",
    "ilorin": "Kwara",
    "onitsha": "Anambra",
    "warri": "Delta",
    "calabar": "Cross River",
    "uyo": "Akwa Ibom",
    "owerri": "Imo",
    "enugu": "Enugu",
    "abeokuta": "Ogun",
    "makurdi": "Benue",
    "yola": "Adamawa",
    "lafia": "Nasarawa",
    "keffi": "Nasarawa",
    "suleja": "Niger",
    "minna": "Niger",
    "lokoja": "Kogi",
    "ikeja": "Lagos",
    "lekki": "Lagos",
    "victoria island": "Lagos",
    "surulere": "Lagos",
    "yaba": "Lagos",
    "wuse": "FCT",
    "garki": "FCT",
    "gwarinpa": "FCT",
    "maitama": "FCT",
}

# ── Drug/Medication Gazetteers ───────────────────────────────────────────────

ART_DRUGS = {
    # First-line
    "tenofovir": {"class": "NRTI", "abbreviation": "TDF"},
    "lamivudine": {"class": "NRTI", "abbreviation": "3TC"},
    "dolutegravir": {"class": "INSTI", "abbreviation": "DTG"},
    "emtricitabine": {"class": "NRTI", "abbreviation": "FTC"},
    "efavirenz": {"class": "NNRTI", "abbreviation": "EFV"},
    # Second-line
    "atazanavir": {"class": "PI", "abbreviation": "ATV"},
    "lopinavir": {"class": "PI", "abbreviation": "LPV"},
    "ritonavir": {"class": "PI", "abbreviation": "RTV"},
    "zidovudine": {"class": "NRTI", "abbreviation": "AZT/ZDV"},
    "nevirapine": {"class": "NNRTI", "abbreviation": "NVP"},
    "abacavir": {"class": "NRTI", "abbreviation": "ABC"},
    "darunavir": {"class": "PI", "abbreviation": "DRV"},
    "raltegravir": {"class": "INSTI", "abbreviation": "RAL"},
    # Common abbreviations
    "tdf": {"class": "NRTI", "full_name": "Tenofovir"},
    "3tc": {"class": "NRTI", "full_name": "Lamivudine"},
    "dtg": {"class": "INSTI", "full_name": "Dolutegravir"},
    "ftc": {"class": "NRTI", "full_name": "Emtricitabine"},
    "efv": {"class": "NNRTI", "full_name": "Efavirenz"},
}

PREVENTION_DRUGS = {
    "prep": "Pre-Exposure Prophylaxis",
    "pre-exposure prophylaxis": "PrEP",
    "pep": "Post-Exposure Prophylaxis",
    "post-exposure prophylaxis": "PEP",
    "truvada": "PrEP (Tenofovir/Emtricitabine)",
}

# ── Service Types ────────────────────────────────────────────────────────────

SERVICE_TYPE_PATTERNS = {
    "HTS": [r"\b(hiv\s*test|testing|hts|vct|get\s*tested|check\s*(my\s*)?status)\b"],
    "ART": [r"\b(art\b|antiretroviral|treatment|arv|medication)\b"],
    "PrEP": [r"\b(prep|pre.exposure|prevention\s*pill|prevention\s*medication)\b"],
    "PEP": [r"\b(pep|post.exposure|emergency\s*prevention)\b"],
    "PMTCT": [r"\b(pmtct|mother.to.child|pregnant|pregnancy|antenatal)\b"],
    "VMMC": [r"\b(vmmc|circumcision|male\s*circumcision)\b"],
    "Counselling": [r"\b(counsel|counselling|counseling|support|mental\s*health|therapy)\b"],
    "TB": [r"\b(tb\b|tuberculosis)\b"],
}

# ── Symptom Descriptors ─────────────────────────────────────────────────────

SYMPTOM_PATTERNS = [
    r"\b(fever|temperature|hot)\b",
    r"\b(rash|skin|sore|lesion|blister)\b",
    r"\b(weight\s*loss|losing\s*weight|thin|wasting)\b",
    r"\b(cough|coughing|chest\s*pain)\b",
    r"\b(fatigue|tired|exhausted|weakness|weak)\b",
    r"\b(swollen|swelling|lymph\s*node|gland)\b",
    r"\b(diarrhoea|diarrhea|vomiting|nausea)\b",
    r"\b(headache|head\s*ache|migraine)\b",
    r"\b(night\s*sweat|sweating)\b",
    r"\b(mouth\s*sore|oral\s*thrush|thrush)\b",
]


def extract_entities(text: str) -> ExtractedEntities:
    """
    Extract all named entities from user message text.
    Returns an ExtractedEntities object with locations, drugs,
    service types, and symptoms found.
    """
    text_lower = text.lower().strip()
    entities = ExtractedEntities()

    # ── Extract locations ──
    entities.locations = _extract_locations(text_lower)

    # ── Extract drug mentions ──
    entities.drugs = _extract_drugs(text_lower)

    # ── Extract service types ──
    entities.service_types = _extract_service_types(text_lower)

    # ── Extract symptoms ──
    entities.symptoms = _extract_symptoms(text_lower)

    # Build raw dict
    entities.raw = entities.to_dict()

    if any([entities.locations, entities.drugs, entities.service_types, entities.symptoms]):
        logger.debug(
            "entities_extracted",
            locations=len(entities.locations),
            drugs=len(entities.drugs),
            services=len(entities.service_types),
            symptoms=len(entities.symptoms),
        )

    return entities


def _extract_locations(text: str) -> list[dict]:
    """Extract Nigerian state and city mentions."""
    found = []
    seen = set()

    # Check cities first (more specific)
    for city, state in MAJOR_CITIES.items():
        if city in text and city not in seen:
            found.append({"city": city.title(), "state": state, "type": "city"})
            seen.add(city)
            seen.add(state.lower())

    # Check states
    for state in NIGERIAN_STATES:
        if state in text and state not in seen:
            found.append({"state": state.title(), "type": "state"})
            seen.add(state)

    return found


def _extract_drugs(text: str) -> list[str]:
    """Extract ART drug name and prevention medication mentions."""
    found = []
    seen = set()

    for drug in ART_DRUGS:
        if drug in text and drug not in seen:
            info = ART_DRUGS[drug]
            name = info.get("full_name", drug.title())
            found.append(name)
            seen.add(drug)

    for drug in PREVENTION_DRUGS:
        if drug in text and drug not in seen:
            found.append(drug.upper() if len(drug) <= 4 else drug.title())
            seen.add(drug)

    return found


def _extract_service_types(text: str) -> list[str]:
    """Extract HIV service type mentions."""
    found = []
    for service, patterns in SERVICE_TYPE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                if service not in found:
                    found.append(service)
                break
    return found


def _extract_symptoms(text: str) -> list[str]:
    """Extract symptom/health complaint mentions."""
    found = []
    for pattern in SYMPTOM_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            symptom = match.group(0).strip()
            if symptom not in found:
                found.append(symptom)
    return found
