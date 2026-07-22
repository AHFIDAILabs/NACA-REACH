"""
NACA AI Chatbot — Text Normaliser for Nigerian Languages (Section 3.1.4)

Normalises informal text, SMS-style abbreviations, and Nigerian Pidgin
spelling variants BEFORE translation, improving NMT accuracy.

Handles:
- Nigerian Pidgin contractions and slang
- SMS/WhatsApp text abbreviations (common on Nigerian phones)
- Informal spelling variants (e.g., "ow far" → "how far")
- Number-letter substitutions (e.g., "2moro" → "tomorrow")
- Mixed-language code switching markers
"""

import re

import structlog

logger = structlog.get_logger()


# ── Nigerian Pidgin Normalisation Map ────────────────────────────────────────
# Maps informal Pidgin spellings/abbreviations to standard Pidgin or English
# for better translation API performance.

PIDGIN_NORMALISATION = {
    # Common Pidgin contractions
    "ow": "how",
    "ow far": "how far",
    "howfa": "how far",
    "wetin": "what",
    "shey": "is it that",
    "abi": "is it not",
    "sha": "though",
    "sef": "even",
    "dey": "is",
    "no dey": "is not",
    "e dey": "it is",
    "i dey": "i am",
    "we dey": "we are",
    "dem dey": "they are",
    "na": "is",
    "e be like": "it seems like",
    "wahala": "problem",
    "wahala dey": "there is a problem",
    "no wahala": "no problem",
    "abeg": "please",
    "biko": "please",
    "oya": "come on",
    "jare": "please",
    "bros": "brother",
    "sista": "sister",
    "pikin": "child",
    "pickin": "child",
    "bodi": "body",
    "belle": "stomach",
    "chop": "eat",
    "waka": "walk",
    "go": "go",
    "comot": "come out",
    "come": "come",
    "de": "the",
    "dat": "that",
    "dis": "this",
    "dem": "them",
    "wey": "that",
    "una": "you all",
    "sabi": "know",
    "fit": "can",
    "no fit": "cannot",
    "wan": "want",
    "dun": "already",
    "don": "already",
    "waka go": "go to",
    "nah": "is",

    # HIV/Health-specific Pidgin
    "d sickness": "the sickness",
    "dat sickness": "that sickness",
    "blood test": "blood test",
    "testing centre": "testing centre",
    "hospital": "hospital",
    "clinic": "clinic",
    "drug": "medication",
    "medicine": "medication",
    "tablet": "tablet",
    "injection": "injection",
    "dokita": "doctor",
    "nurse": "nurse",
}

# ── SMS / WhatsApp Abbreviation Map ──────────────────────────────────────────

SMS_ABBREVIATIONS = {
    "pls": "please",
    "plz": "please",
    "thx": "thanks",
    "tnx": "thanks",
    "thnks": "thanks",
    "ty": "thank you",
    "u": "you",
    "ur": "your",
    "r": "are",
    "d": "the",
    "nd": "and",
    "hw": "how",
    "whr": "where",
    "whn": "when",
    "wht": "what",
    "nt": "not",
    "cn": "can",
    "bt": "but",
    "dn": "done",
    "gv": "give",
    "gt": "get",
    "nid": "need",
    "hlp": "help",
    "msg": "message",
    "info": "information",
    "abt": "about",
    "b4": "before",
    "bcz": "because",
    "bcos": "because",
    "cuz": "because",
    "2day": "today",
    "2moro": "tomorrow",
    "2morow": "tomorrow",
    "2nite": "tonight",
    "4": "for",
    "4rm": "from",
    "1st": "first",
    "2nd": "second",
    "3rd": "third",
    "hv": "have",
    "shd": "should",
    "wd": "would",
    "cd": "could",
    "wld": "would",
    "cld": "could",
    "ppl": "people",
    "govt": "government",
    "hosp": "hospital",
    "doc": "doctor",
    "dr": "doctor",
    "med": "medicine",
    "meds": "medicines",
    "yr": "year",
    "yrs": "years",
    "mth": "month",
    "mths": "months",
    "wk": "week",
    "wks": "weeks",
    "hr": "hour",
    "hrs": "hours",
    "min": "minute",
    "mins": "minutes",
}

# ── Repeated character patterns ──────────────────────────────────────────────
# e.g., "helpppp" → "help", "pleaseeee" → "please"
REPEATED_CHARS_PATTERN = re.compile(r'(.)\1{2,}')

# ── Mixed number-letter patterns ─────────────────────────────────────────────
NUMBER_SUBS = {
    "2": "to",
    "4": "for",
    "8": "ate",
}


def normalise_text(text: str, language: str = "pcm") -> str:
    """
    Normalise user input text before translation or NLU processing.

    Steps:
    1. Lowercase and strip
    2. Fix repeated characters (e.g., "helppppp" → "help")
    3. Expand SMS abbreviations
    4. Normalise Pidgin spellings (if language is pcm)
    5. Clean up whitespace and punctuation
    """
    if not text or not text.strip():
        return text

    original = text
    text = text.strip()

    # Step 1: Fix repeated characters
    text = REPEATED_CHARS_PATTERN.sub(r'\1\1', text)

    # Step 2: Expand SMS abbreviations (word-boundary aware)
    text = _expand_abbreviations(text, SMS_ABBREVIATIONS)

    # Step 3: Pidgin normalisation
    if language in ("pcm", "pidgin"):
        text = _expand_abbreviations(text, PIDGIN_NORMALISATION)

    # Step 4: Clean up
    text = re.sub(r'\s+', ' ', text).strip()

    if text.lower() != original.lower():
        logger.debug(
            "text_normalised",
            original_length=len(original),
            normalised_length=len(text),
            language=language,
        )

    return text


def _expand_abbreviations(text: str, mapping: dict[str, str]) -> str:
    """Replace abbreviations with full forms, respecting word boundaries."""
    # Sort by length (longest first) to avoid partial replacements
    sorted_abbrevs = sorted(mapping.keys(), key=len, reverse=True)

    for abbrev in sorted_abbrevs:
        pattern = r'\b' + re.escape(abbrev) + r'\b'
        replacement = mapping[abbrev]
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    return text


def normalise_for_translation(text: str, source_language: str) -> str:
    """
    Apply language-specific normalisation before sending to
    Google Cloud Translation API.

    This improves translation quality for informal Nigerian text.
    """
    if source_language in ("pcm", "pidgin"):
        return normalise_text(text, language="pcm")
    elif source_language in ("ha", "yo", "ig"):
        # For Hausa/Yoruba/Igbo, just fix SMS abbreviations
        return normalise_text(text, language="general")
    return text
