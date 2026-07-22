"""
NACA AI Chatbot — Translation Service (Section 3.1.4)

Google Cloud Translation API v3 integration for multilingual support.
Handles inbound (user language → English) and outbound (English → user language)
translation for Hausa, Yoruba, Igbo, and Nigerian Pidgin.

Knowledge base is stored in English; translation is applied only at the
user-facing layer to maintain clinical accuracy.
"""

import structlog

from src.core.config import get_settings
from src.schemas.messages import SupportedLanguage

logger = structlog.get_logger()
settings = get_settings()

# Google Cloud Translation language codes
_LANGUAGE_CODES = {
    SupportedLanguage.ENGLISH: "en",
    SupportedLanguage.HAUSA: "ha",
    SupportedLanguage.YORUBA: "yo",
    SupportedLanguage.IGBO: "ig",
    SupportedLanguage.PIDGIN: "pcm",
}

# Fallback message when translation fails (Section 3.1.4)
TRANSLATION_FALLBACK = (
    "I am responding in English as I could not translate your message accurately. "
    "Please try rephrasing your message or type in English."
)


class TranslationService:
    """
    Translates text between English and Nigerian languages using
    Google Cloud Translation API v3.
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        """Lazy-initialise the translation client."""
        if self._client is None:
            try:
                from google.cloud import translate_v3 as translate

                self._client = translate.TranslationServiceAsyncClient()
            except Exception as e:
                logger.error("translation_client_init_failed", error=str(e))
                self._client = None
        return self._client

    @property
    def _parent(self) -> str:
        return f"projects/{settings.gcp_project_id}/locations/global"

    async def translate_to_english(
        self, text: str, source_language: SupportedLanguage
    ) -> str:
        """
        Inbound translation: user language → English.
        Called before NLU processing so the AI pipeline operates in English.
        """
        if source_language == SupportedLanguage.ENGLISH:
            return text

        # Nigerian Pidgin not supported by Google Translation — skip
        if source_language == SupportedLanguage.PIDGIN:
            logger.info("pidgin_skip_translation_using_direct_llm")
            return text

        source_code = _LANGUAGE_CODES.get(source_language, "en")
        return await self._translate(
            text=text,
            source_lang=source_code,
            target_lang="en",
            direction="inbound",
        )

    async def translate_from_english(
        self, text: str, target_language: SupportedLanguage
    ) -> str:
        """
        Outbound translation: English → user language.
        Called after LLM generates an English response.
        """
        if target_language == SupportedLanguage.ENGLISH:
            return text

        # Nigerian Pidgin not supported by Google Translation — respond in English
        if target_language == SupportedLanguage.PIDGIN:
            logger.info("pidgin_skip_outbound_translation")
            return text

        target_code = _LANGUAGE_CODES.get(target_language, "en")
        return await self._translate(
            text=text,
            source_lang="en",
            target_lang=target_code,
            direction="outbound",
        )

    async def _translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        direction: str,
    ) -> str:
        """
        Core translation method using Google Cloud Translation API v3.
        Falls back to original text with a notice on failure.
        """
        client = self._get_client()

        if not client:
            logger.warning(
                "translation_unavailable",
                direction=direction,
                source=source_lang,
                target=target_lang,
            )
            if direction == "outbound":
                return text  # Return English response if outbound translation fails
            return text  # Return original text if inbound fails

        try:
            from google.cloud import translate_v3 as translate

            request = translate.TranslateTextRequest(
                parent=self._parent,
                contents=[text],
                source_language_code=source_lang,
                target_language_code=target_lang,
                mime_type="text/plain",
            )

            response = await client.translate_text(request=request)

            if response.translations:
                translated = response.translations[0].translated_text
                logger.info(
                    "translation_success",
                    direction=direction,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    input_chars=len(text),
                    output_chars=len(translated),
                )
                return translated

            logger.warning("translation_empty_response", direction=direction)
            return text

        except Exception as e:
            logger.error(
                "translation_failed",
                direction=direction,
                source_lang=source_lang,
                target_lang=target_lang,
                error=str(e),
            )
            # Fallback: return original text
            if direction == "inbound":
                return text
            # For outbound, prepend the fallback notice
            return f"{TRANSLATION_FALLBACK}\n\n{text}"
