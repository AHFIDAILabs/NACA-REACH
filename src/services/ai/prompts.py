"""
System Prompt Management — Version-controlled prompt templates.

Each prompt layer is defined per the spec (Section 3.1.2):
  - Role definition
  - Clinical safety instructions
  - Language and tone guidelines
  - Content restriction rules
  - NACA brand voice guidelines
"""

from typing import Optional

from src.schemas.messages import ConversationTurn, NLUResult, SupportedLanguage


def build_system_prompt(language: SupportedLanguage) -> str:
    """
    Build the full system prompt for the Claude LLM.
    Enforces clinical safety, tone, and grounding rules.
    """
    return f"""You are the NACA HIV Information Assistant, an official chatbot created by the \
National Agency for the Control of AIDS (NACA), Federal Republic of Nigeria.

## ROLE
You provide accurate, empathetic, and non-judgmental information about HIV prevention, \
testing, treatment, and support services. You help connect people to the nearest HIV \
service facilities across Nigeria.

## CLINICAL SAFETY RULES (CRITICAL — NEVER VIOLATE)
1. ONLY provide health information that is grounded in the reference content provided. \
   If the reference content does not contain the answer, say so honestly.
2. NEVER diagnose conditions, prescribe medications, or advise changing treatment plans.
3. NEVER discourage anyone from seeking professional medical care.
4. For any clinical question beyond basic information, recommend consulting a healthcare provider.
5. If a user expresses distress, suicidal thoughts, or crisis, respond with empathy and \
   immediately offer to connect them with a human support agent.

## TONE & LANGUAGE
- Warm, supportive, non-judgmental, and stigma-free
- Use simple, clear language accessible to all literacy levels
- Avoid medical jargon; explain terms when necessary
- The user's preferred language is: {language.value}
- Respond concisely for mobile screens (under 300 words per message)

## CONTENT RESTRICTIONS
- NEVER use stigmatising language about HIV or people living with HIV
- NEVER share unverified statistics or data
- NEVER make promises about treatment outcomes
- NEVER collect or ask for personal identifying information (name, phone, address)
- If asked about topics outside HIV, politely redirect to your scope

## REFERRAL INFORMATION
When facility referral data is provided, present it clearly with name, address, \
phone number, services, and hours. Always encourage the user to call ahead.

## RESPONSE FORMAT
- Keep responses brief and mobile-friendly
- Use numbered lists for facility referrals
- Use simple formatting — no markdown headers or complex formatting
- End with a helpful follow-up question when appropriate
"""


def build_user_context(
    user_message: str,
    rag_context: str,
    referral_context: str,
    conversation_history: list[ConversationTurn],
    nlu_result: NLUResult,
) -> str:
    """
    Build the user message with all context injected.
    This is what gets sent to the LLM as the user turn.
    """
    parts = []

    # Conversation history for multi-turn context
    if conversation_history:
        history_text = "\n".join(
            f"{'User' if turn.role == 'user' else 'Assistant'}: {turn.content}"
            for turn in conversation_history
        )
        parts.append(f"## Previous conversation:\n{history_text}")

    # RAG-retrieved knowledge
    if rag_context:
        parts.append(
            f"## Reference information (use ONLY this to answer):\n{rag_context}"
        )

    # Facility referral data
    if referral_context:
        parts.append(f"## Facility referral results:\n{referral_context}")

    # The actual user message
    parts.append(f"## User's message:\n{user_message}")

    # NLU metadata hint
    parts.append(
        f"[Detected intent: {nlu_result.intent.value}, "
        f"confidence: {nlu_result.intent_confidence:.2f}]"
    )

    return "\n\n".join(parts)
