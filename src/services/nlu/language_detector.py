"""
NACA AI Chatbot — Language Detector (Section 3.1.4)

Detects user's language from incoming text.
Supports: English, Hausa, Yoruba, Igbo, Nigerian Pidgin.
"""

import re
import structlog
from src.schemas.messages import SupportedLanguage

logger = structlog.get_logger()

# Common marker words/phrases for each language
_LANGUAGE_MARKERS = {
    SupportedLanguage.HAUSA: {
        "ina", "na", "yaya", "sannu", "nagode", "ko", "ba", "shi", "ta",
        "wannan", "wane", "mene", "kai", "ke", "mu", "su", "zan", "zai",
        "allah", "lafiya", "asibiti", "gwajin", "cutar", "kanjamau",
    },
    SupportedLanguage.YORUBA: {
        "ẹ", "ṣe", "jọwọ", "bawo", "ni", "ọjọ", "ọmọ", "ile", "iwọ",
        "emi", "awa", "won", "kini", "nibo", "nigbati", "pelu", "ati",
        "arun", "idanwo", "oogun", "ile-iwosan",
    },
    SupportedLanguage.IGBO: {
        "kedu", "biko", "ọ", "nke", "na", "gị", "anyị", "ha", "ebe",
        "olee", "maka", "nwere", "ike", "ọrịa", "ụlọ", "ọgwụ", "nlele",
    },
    SupportedLanguage.PIDGIN: {
        "wetin", "dey", "abeg", "wahala", "sef", "una", "sha", "shey",
        "abi", "na", "e", "no", "dem", "wey", "sabi", "chop", "pikin",
        "bodi", "hospital", "test", "medicine",
    },
}


def detect_language(text: str) -> SupportedLanguage:
    """
    Detect language from text using keyword matching.
    
    For production, this should be enhanced with a proper language
    identification model (e.g., fastText lid.176.bin) trained on
    Nigerian language data. This keyword-based approach is a
    functional placeholder.
    """
    if not text or len(text.strip()) < 2:
        return SupportedLanguage.ENGLISH

    text_lower = text.lower().strip()
    words = set(re.findall(r'\w+', text_lower))

    # Score each language by marker word overlap
    scores = {}
    for lang, markers in _LANGUAGE_MARKERS.items():
        overlap = words & markers
        if overlap:
            # Weight by proportion of message that matches
            scores[lang] = len(overlap) / max(len(words), 1)

    if scores:
        best_lang = max(scores, key=scores.get)
        best_score = scores[best_lang]

        # Require minimum confidence to avoid false positives
        if best_score >= 0.15:
            logger.debug(
                "language_detected",
                language=best_lang.value,
                score=round(best_score, 3),
            )
            return best_lang

    # Default to English
    return SupportedLanguage.ENGLISH
