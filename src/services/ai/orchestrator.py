"""
NACA AI Chatbot — AI Orchestrator (Section 3.1, 3.2.0)

The central orchestration service managing the full request lifecycle:
Message → Language Detection → Translation → NLU → Escalation Check →
Agentic RAG → LLM → Safety Check → Translation → Response

This is the "brain" of the system.
"""

import uuid
import time

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.redis_client import SessionStore
from src.schemas.messages import (
    IncomingMessage,
    BotResponse,
    EscalationResponse,
    SessionState,
    SupportedLanguage,
    ResponseType,
    ModelTier,
    IntentCategory,
)
from src.services.ai.llm_client import LLMClient, FALLBACK_RESPONSES
from src.services.nlu.pipeline import process_nlu
from src.services.nlu.language_detector import detect_language
from src.services.translation.translator import TranslationService
from src.services.escalation.escalation_service import EscalationService
from src.services.rag.agent_tools import AgentToolRegistry, synthesize_tool_results
from src.services.ai.faithfulness import FaithfulnessScorer
from src.services.ai.conversation_flows import (
    is_greeting_or_start, resolve_quick_action, build_welcome_response,
    build_exposure_checker_response,
)

logger = structlog.get_logger()
settings = get_settings()


class AIOrchestrator:
    """
    Orchestrates the full AI processing pipeline for each user message.
    Implements the Agentic RAG reasoning loop described in Section 3.2.0.
    """

    def __init__(self, db: AsyncSession, session_store: SessionStore):
        self.db = db
        self.session_store = session_store
        self.llm = LLMClient()
        self.translator = TranslationService()
        self.escalation_service = EscalationService(db)

    async def process(
        self, message: IncomingMessage, session: SessionState
    ) -> BotResponse:
        """
        Full processing pipeline for a single user message.
        """
        start_time = time.time()
        response_id = str(uuid.uuid4())

        try:
            # ── Fast path: Greetings return welcome message instantly (no LLM) ──
            if is_greeting_or_start(message.text):
                user_name = message.user_name
                # Also check session for stored name
                if not user_name and session.referral_state:
                    user_name = session.referral_state.get("user_name")
                # Store name in session for future use
                if user_name:
                    session.referral_state = session.referral_state or {}
                    session.referral_state["user_name"] = user_name
                    await self.session_store.update_session(session)

                return build_welcome_response(
                    session_id=session.session_id,
                    language=session.language,
                    user_name=user_name,
                )

            # ── Fast path: Quick action button presses ──
            expanded = resolve_quick_action(message.text)
            if expanded:
                message.text = expanded

            # ── Fast path: Exposure checker ──
            if message.text.strip() == "action_exposed":
                return build_exposure_checker_response(
                    session_id=session.session_id,
                    language=session.language,
                )

            # ── Step 1: Unified NLU pipeline (detect, normalise, classify, extract) ──
            nlu_result = await process_nlu(
                text=message.text,
                language_hint=message.language_hint,
            )
            detected_lang = nlu_result.detected_language
            session.detected_language = detected_lang

            # ── Step 2: Translate to English (if needed) ──
            english_text = message.text
            needs_translation = (
                detected_lang != SupportedLanguage.ENGLISH
                and settings.translation_enabled
            )
            if detected_lang == SupportedLanguage.HAUSA and settings.hausa_direct_llm:
                needs_translation = False

            if needs_translation:
                english_text = await self.translator.translate_to_english(
                    text=message.text,
                    source_language=detected_lang,
                )
                # Re-run NLU on English text for better intent accuracy
                nlu_result = await process_nlu(text=english_text)
                nlu_result.detected_language = detected_lang

            # ── Step 3: Escalation check ──
            if nlu_result.requires_escalation:
                return await self._handle_escalation(
                    message=message,
                    session=session,
                    nlu_result=nlu_result,
                    detected_lang=detected_lang,
                )

            # ── Step 5: Handle opt-out ──
            if nlu_result.intent == IntentCategory.OPT_OUT:
                return self._build_opt_out_response(
                    response_id=response_id,
                    session=session,
                    language=detected_lang,
                )

            # ── Step 6: Agentic RAG — plan and execute tools ──
            agent = AgentToolRegistry(db=self.db)
            plan = agent.plan_tools(query=english_text, intent=nlu_result.intent)
            tool_results = await agent.execute_plan(
                query=english_text,
                plan=plan,
                session=session,
                latitude=message.location_data.latitude if message.location_data else None,
                longitude=message.location_data.longitude if message.location_data else None,
                service_type=nlu_result.entities.get("service_type"),
            )
            retrieved_context = synthesize_tool_results(tool_results)

            # ── Step 7: Select model tier and generate response ──
            model_name, model_tier = self.llm.select_model(
                intent=nlu_result.intent.value,
                confidence=nlu_result.intent_confidence,
            )

            # Build conversation history for context
            history = [
                {"role": t.role, "content": t.content}
                for t in session.conversation_history[-10:]
            ]

            llm_result = await self.llm.generate(
                user_message=english_text,
                conversation_history=history,
                retrieved_context=retrieved_context,
                model_tier=model_tier,
            )

            response_text = llm_result["text"]

            # ── Step 8: Faithfulness check ──
            faithfulness = FaithfulnessScorer()
            response_text, faith_result = faithfulness.validate_and_sanitise(
                response_text=response_text,
                source_context=retrieved_context,
            )

            # ── Step 9: Translate response back to user language ──
            if needs_translation:
                response_text = await self.translator.translate_from_english(
                    text=response_text,
                    target_language=detected_lang,
                )

            latency_ms = int((time.time() - start_time) * 1000)

            return BotResponse(
                response_id=response_id,
                session_id=session.session_id,
                text=response_text,
                language=detected_lang,
                response_type=ResponseType.TEXT,
                metadata={
                    "intent": nlu_result.intent.value,
                    "confidence": nlu_result.intent_confidence,
                    "model_used": model_tier.value,
                    "latency_ms": latency_ms,
                },
            )

        except Exception as e:
            logger.error("orchestrator_error", error=str(e), exc_info=True)
            # Return safe fallback response
            lang = session.detected_language or SupportedLanguage.ENGLISH
            return BotResponse(
                response_id=response_id,
                session_id=session.session_id,
                text=FALLBACK_RESPONSES.get(lang.value, FALLBACK_RESPONSES["en"]),
                language=lang,
                response_type=ResponseType.TEXT,
                metadata={"error": True},
            )

    async def _handle_escalation(
        self, message, session, nlu_result, detected_lang
    ) -> BotResponse:
        """
        Handle escalation:
        1. Create escalation ticket
        2. Alert all counsellors via WhatsApp with conversation context
        3. Give user the counsellor's WhatsApp number
        4. Return BotResponse (not EscalationResponse) so bot stays active
        """
        from src.schemas.messages import EscalationRequest

        response_id = str(uuid.uuid4())

        request = EscalationRequest(
            session_id=session.session_id,
            trigger_type=nlu_result.escalation_trigger,
            priority=nlu_result.escalation_priority,
            trigger_details={"distress_level": nlu_result.distress_level},
            conversation_history=[
                {"role": t.role, "content": t.content}
                for t in session.conversation_history
            ],
        )

        ticket = await self.escalation_service.create_ticket(request)

        # ── Alert counsellors via WhatsApp ──
        counsellor_numbers = settings.counsellor_whatsapp_numbers
        if counsellor_numbers:
            await self._notify_counsellors(
                counsellor_numbers=counsellor_numbers,
                session=session,
                nlu_result=nlu_result,
                message=message,
                ticket_id=str(ticket.ticket_id),
            )

        # ── Build user-facing response with counsellor contact ──
        # Extract counsellor phone numbers (strip whatsapp: prefix for display)
        display_numbers = []
        if counsellor_numbers:
            for num in counsellor_numbers.split(","):
                clean = num.strip().replace("whatsapp:", "")
                display_numbers.append(clean)

        counsellor_contact = ""
        if display_numbers:
            numbers_text = "\n".join(f"📞 {n}" for n in display_numbers)
            counsellor_contact = (
                f"\n\n*You can also reach our trained counsellors directly on WhatsApp:*\n"
                f"{numbers_text}\n\n"
                f"Simply save the number and send them a message on WhatsApp. "
                f"They have been notified and are ready to help you."
            )

        holding_messages = {
            "en": (
                f"I hear you, and I want you to know that support is available. 💙\n\n"
                f"I've alerted our trained {settings.counsellor_display_name} "
                f"who can provide personal, confidential support."
                f"{counsellor_contact}\n\n"
                f"I'm still here too — you can continue to ask me questions anytime."
            ),
            "ha": (
                f"Na ji ku, kuma ina so ku san cewa akwai taimako. 💙\n\n"
                f"Na sanar da {settings.counsellor_display_name} "
                f"wanda zai iya taimaka muku."
                f"{counsellor_contact}\n\n"
                f"Har yanzu ina nan — za ku iya ci gaba da tambayata."
            ),
            "pcm": (
                f"I hear you, and I wan make you know say help dey available. 💙\n\n"
                f"I don alert our {settings.counsellor_display_name} "
                f"wey fit give you personal support."
                f"{counsellor_contact}\n\n"
                f"I still dey here too — you fit still dey ask me questions."
            ),
        }

        response_text = holding_messages.get(
            detected_lang.value, holding_messages["en"]
        )

        return BotResponse(
            response_id=response_id,
            session_id=session.session_id,
            text=response_text,
            language=detected_lang,
            response_type=ResponseType.TEXT,
            metadata={
                "escalation": True,
                "ticket_id": str(ticket.ticket_id),
                "priority": nlu_result.escalation_priority.value if nlu_result.escalation_priority else None,
            },
        )

    async def _notify_counsellors(
        self, counsellor_numbers: str, session, nlu_result, message, ticket_id: str
    ):
        """Send escalation alert to all counsellor WhatsApp numbers."""
        from src.services.channels.whatsapp import WhatsAppSender
        sender = WhatsAppSender()

        # Build conversation summary from last 5 messages
        recent = session.conversation_history[-5:]
        summary_lines = []
        for t in recent:
            role = "👤 User" if t.role == "user" else "🤖 Bot"
            summary_lines.append(f"{role}: {t.content[:200]}")
        conversation_summary = "\n".join(summary_lines) if summary_lines else "No prior messages"

        priority = nlu_result.escalation_priority.value if nlu_result.escalation_priority else "P3_MEDIUM"
        trigger = nlu_result.escalation_trigger.value if nlu_result.escalation_trigger else "UNKNOWN"

        alert_text = (
            f"🚨 *NACA-REACH Escalation Alert*\n\n"
            f"*Priority:* {priority}\n"
            f"*Trigger:* {trigger}\n"
            f"*Distress Level:* {nlu_result.distress_level}/10\n"
            f"*Channel:* {message.channel.value}\n"
            f"*Ticket ID:* {ticket_id}\n\n"
            f"📝 *Recent Conversation:*\n"
            f"{conversation_summary}\n\n"
            f"Please reach out to this user as soon as possible."
        )

        # Create a simple BotResponse to send via the sender
        alert_response = BotResponse(
            response_id=f"alert-{ticket_id}",
            session_id="counsellor-alert",
            text=alert_text,
            language=SupportedLanguage.ENGLISH,
            response_type=ResponseType.TEXT,
        )

        # Send to all counsellors
        for number in counsellor_numbers.split(","):
            number = number.strip()
            if number:
                try:
                    await sender.send(to_number=number, response=alert_response)
                    logger.info("counsellor_notified", number=number[:15] + "***")
                except Exception as e:
                    logger.error("counsellor_notification_failed", number=number[:15] + "***", error=str(e))

    def _build_opt_out_response(
        self, response_id: str, session: SessionState, language: SupportedLanguage
    ) -> BotResponse:
        """Handle user opt-out request."""
        messages = {
            "en": "You have been opted out and will no longer receive messages. If you ever need support again, simply send a new message. Take care.",
            "ha": "An cire ku daga jerin. Ba za ku sake samun saƙonni ba. Idan kuna buƙatar taimako a nan gaba, kawai ku aika da sabon saƙo.",
            "yo": "A ti yọ ọ kuro. Iwọ kii yoo gba awọn ifiranṣẹ mọ. Ti o ba nilo atilẹyin lẹẹkansi, kan fi ifiranṣẹ tuntun ranṣẹ.",
            "ig": "Ewepụla gị. Ị gaghị anata ozi ọzọ. Ọ bụrụ na ịchọrọ nkwado ọzọ, zipu ozi ọhụrụ.",
            "pcm": "We don remove you. You no go receive message again. If you need help for future, just send new message.",
        }
        return BotResponse(
            response_id=response_id,
            session_id=session.session_id,
            text=messages.get(language.value, messages["en"]),
            language=language,
            response_type=ResponseType.TEXT,
        )
