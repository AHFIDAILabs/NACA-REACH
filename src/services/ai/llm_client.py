"""
NACA AI Chatbot — LLM Client (Anthropic Claude)

Tiered model routing: Claude Haiku 4.5 for simple queries (~70%),
Claude Sonnet 4.6 for complex/clinical queries (~30%).
See: Section 2.3, 3.1.2
"""

import time
from enum import Enum

import anthropic
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from src.core.config import get_settings
from src.schemas.messages import ModelTier

logger = structlog.get_logger()
settings = get_settings()


# System prompt layers as defined in Section 3.1.2
SYSTEM_PROMPT = """You are the NACA HIV Support Assistant, an AI chatbot created by the 
National Agency for the Control of AIDS (NACA), Federal Republic of Nigeria.

## Role
You provide accurate, compassionate, and non-judgemental HIV-related information 
and support to people in Nigeria. You help with:
- HIV prevention information (PrEP, PEP, condom use, PMTCT)
- HIV testing guidance and facility referrals
- ART treatment information and adherence support
- Myth correction with evidence-based facts
- Emotional support and crisis navigation

## Clinical Safety Rules
1. NEVER diagnose or prescribe. You provide information, not medical advice.
2. ALWAYS recommend consulting a healthcare provider for clinical decisions.
3. For drug interactions, side effects, or treatment changes: escalate to a human agent.
4. NEVER generate stigmatising, discriminatory, or shaming language about HIV status.
5. If a user expresses suicidal thoughts, self-harm, or severe distress: 
   immediately trigger escalation to a human agent.

## Content Rules
- Ground ALL responses strictly in the retrieved knowledge base content provided.
- If the knowledge base does not contain relevant information, say so honestly.
- Do NOT invent statistics, drug names, facility names, or clinical protocols.
- Keep responses concise and mobile-friendly (under 300 words).
- Use simple, clear language accessible to users with varying literacy levels.

## Tone
- Warm, supportive, and non-judgemental
- Respectful of privacy — never ask for personal identifying information
- Culturally sensitive to Nigerian contexts
- Use the NACA brand voice: authoritative yet approachable

## Response Format
- Use short paragraphs (2-3 sentences each)
- Use bullet points for lists of options or steps
- Include a clear call-to-action when appropriate (e.g., "Would you like to find a testing centre near you?")
"""


class LLMClient:
    """
    Anthropic Claude client with tiered model routing.
    
    Routes queries to either:
    - Claude Haiku 4.5: Fast, cheap, for simple FAQ-type queries
    - Claude Sonnet 4.6: Powerful, for complex clinical/multi-domain queries
    """

    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.sonnet_model = settings.claude_sonnet_model
        self.haiku_model = settings.claude_haiku_model

    def select_model(self, intent: str, confidence: float) -> tuple[str, ModelTier]:
        """
        Route to the appropriate model tier based on query complexity.
        
        Haiku (fast, cheap): greetings, simple FAQs, language changes, opt-outs
        Sonnet (powerful): clinical queries, multi-domain, low confidence, crisis
        """
        simple_intents = {
            "greeting", "language_change", "opt_out", "general_enquiry", "unknown",
        }
        complex_intents = {
            "treatment", "crisis", "myth_busting",
        }

        if intent in complex_intents or confidence < 0.7:
            return self.sonnet_model, ModelTier.SONNET
        if intent in simple_intents and confidence >= 0.8:
            return self.haiku_model, ModelTier.HAIKU
        # Default: use Haiku for prevention, testing, referral with good confidence
        if confidence >= 0.7:
            return self.haiku_model, ModelTier.HAIKU
        return self.sonnet_model, ModelTier.SONNET

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def generate(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
        retrieved_context: str = "",
        model_tier: ModelTier = ModelTier.HAIKU,
        temperature: float | None = None,
    ) -> dict:
        """
        Generate a response from Claude.
        
        Returns dict with: text, model_used, input_tokens, output_tokens, latency_ms
        """
        model = self.sonnet_model if model_tier == ModelTier.SONNET else self.haiku_model
        temp = temperature or settings.llm_temperature

        # Build messages array with conversation history
        messages = []
        if conversation_history:
            # Include last 10 turns for context
            for turn in conversation_history[-10:]:
                messages.append({
                    "role": turn["role"],
                    "content": turn["content"],
                })

        # Build the user message with retrieved context
        augmented_message = user_message
        if retrieved_context:
            augmented_message = (
                f"## Retrieved Knowledge Base Content\n"
                f"{retrieved_context}\n\n"
                f"## User Question\n"
                f"{user_message}\n\n"
                f"Answer the user's question using ONLY the retrieved content above. "
                f"If the content doesn't cover the question, say so honestly."
            )

        messages.append({"role": "user", "content": augmented_message})

        start_time = time.time()

        try:
            response = await self.client.messages.create(
                model=model,
                max_tokens=settings.llm_max_output_tokens,
                temperature=temp,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
            latency_ms = int((time.time() - start_time) * 1000)

            result_text = response.content[0].text if response.content else ""

            logger.info(
                "llm_response_generated",
                model=model,
                tier=model_tier.value,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_ms=latency_ms,
            )

            return {
                "text": result_text,
                "model_used": model_tier,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "latency_ms": latency_ms,
            }

        except anthropic.APIError as e:
            logger.error("llm_api_error", error=str(e), model=model)
            raise


# Fallback responses when LLM is unavailable
FALLBACK_RESPONSES = {
    "en": "I'm having trouble processing your message right now. Please try again in a moment, or type 'agent' to speak with a human support agent.",
    "ha": "Ina fuskantar matsala wajen aiwatar da sakonku a yanzu. Da fatan za a sake gwadawa, ko rubuta 'agent' don yin magana da wakili.",
    "yo": "Mo n ni isoro lati ṣe ilana ifiranṣẹ rẹ ni bayi. Jọwọ gbiyanju lẹẹkansi, tabi tẹ 'agent' lati ba aṣoju sọrọ.",
    "ig": "Enwere m nsogbu ịhazi ozi gị ugbu a. Biko nwaa ọzọ, ma ọ bụ pịnye 'agent' iji kwurịta okwu na onye nnọchiteanya.",
    "pcm": "I dey find am hard to process your message now now. Abeg try again, or type 'agent' make you talk to person wey fit help.",
}
