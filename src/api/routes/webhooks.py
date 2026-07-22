"""
NACA AI Chatbot — Webhook Endpoints

Receives incoming messages from Twilio (WhatsApp) and Telegram Bot API.
Extracts user names for personalised greetings.
"""

import hashlib
import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from src.core.config import get_settings
from src.schemas.messages import Channel, IncomingMessage, MediaType, LocationData

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()


# =============================================================================
# Twilio WhatsApp Webhook
# =============================================================================

@router.post("/whatsapp")
async def twilio_whatsapp_incoming(request: Request):
    """Receives incoming WhatsApp messages via Twilio webhook."""
    form = await request.form()
    form_data = {k: v for k, v in form.items()}

    msg = _extract_twilio_message(form_data)

    if msg:
        logger.info(
            "whatsapp_message_received",
            message_id=msg.message_id,
            session_id=msg.session_id,
            text_preview=msg.text[:50],
        )

        raw_from = form_data.get("From", "")
        await _process_and_reply_whatsapp(msg, raw_from)

    return PlainTextResponse(
        content="<Response></Response>",
        media_type="application/xml",
    )


async def _process_and_reply_whatsapp(msg: IncomingMessage, raw_from: str):
    """Process message through AI pipeline and send WhatsApp reply via Twilio."""
    from src.core.redis_client import get_session_store
    from src.core.database import db_manager
    from src.services.ai.orchestrator import AIOrchestrator
    from src.services.channels.whatsapp import WhatsAppSender

    session_store = get_session_store()

    session = await session_store.get_session(msg.session_id)
    if not session:
        session = await session_store.create_session(
            session_id=msg.session_id,
            channel=msg.channel,
            user_id_hash=msg.user_id_hash,
        )

    await session_store.add_turn(session.session_id, "user", msg.text)

    db_session = db_manager.get_session()
    try:
        orchestrator = AIOrchestrator(db=db_session, session_store=session_store)
        response = await orchestrator.process(message=msg, session=session)

        await session_store.add_turn(session.session_id, "assistant", response.text)

        sender = WhatsAppSender()
        await sender.send(to_number=raw_from, response=response)

    except Exception as e:
        logger.error("whatsapp_processing_error", error=str(e), exc_info=True)
    finally:
        await db_session.close()


def _extract_twilio_message(form_data: dict) -> IncomingMessage | None:
    """
    Parse Twilio's form-encoded webhook into normalised IncomingMessage.
    Extracts ProfileName for personalised greetings.
    """
    try:
        from_number = form_data.get("From", "")
        body = form_data.get("Body", "")
        message_sid = form_data.get("MessageSid", str(uuid.uuid4()))
        latitude = form_data.get("Latitude")
        longitude = form_data.get("Longitude")
        # Twilio provides the WhatsApp profile name
        profile_name = form_data.get("ProfileName", "")

        if not from_number:
            return None

        clean_number = from_number.replace("whatsapp:", "").strip()
        user_hash = hashlib.sha256(clean_number.encode()).hexdigest()

        media_type = MediaType.TEXT
        location = None

        if latitude and longitude:
            try:
                location = LocationData(
                    latitude=float(latitude),
                    longitude=float(longitude),
                )
                media_type = MediaType.LOCATION
                if not body:
                    body = "[Location shared]"
            except (ValueError, TypeError):
                pass

        if not body and not location:
            return None

        return IncomingMessage(
            message_id=message_sid,
            channel=Channel.WHATSAPP,
            user_id_hash=user_hash,
            timestamp=datetime.utcnow(),
            text=body or "",
            media_type=media_type,
            location_data=location,
            session_id=user_hash[:16],
            user_name=profile_name or None,
        )

    except Exception as e:
        logger.error("twilio_payload_parse_error", error=str(e))
        return None


# =============================================================================
# Telegram Bot API Webhook
# =============================================================================

@router.post("/telegram")
async def telegram_incoming(request: Request):
    """Receives incoming Telegram messages via webhook."""
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if settings.telegram_webhook_secret and secret != settings.telegram_webhook_secret:
        logger.warning("telegram_invalid_secret")
        raise HTTPException(status_code=403, detail="Invalid secret token")

    payload = await request.json()
    msg = _extract_telegram_message(payload)

    if msg:
        logger.info(
            "telegram_message_received",
            message_id=msg.message_id,
            session_id=msg.session_id,
            text_preview=msg.text[:50],
        )

        chat_id = str(payload.get("message", {}).get("chat", {}).get("id", ""))
        await _process_and_reply_telegram(msg, chat_id)

    return {"status": "ok"}


async def _process_and_reply_telegram(msg: IncomingMessage, chat_id: str):
    """Process message through AI pipeline and send Telegram reply."""
    from src.core.redis_client import get_session_store
    from src.core.database import db_manager
    from src.services.ai.orchestrator import AIOrchestrator
    from src.services.channels.telegram import TelegramSender

    session_store = get_session_store()

    session = await session_store.get_session(msg.session_id)
    if not session:
        session = await session_store.create_session(
            session_id=msg.session_id,
            channel=msg.channel,
            user_id_hash=msg.user_id_hash,
        )

    await session_store.add_turn(session.session_id, "user", msg.text)

    db_session = db_manager.get_session()
    try:
        orchestrator = AIOrchestrator(db=db_session, session_store=session_store)
        response = await orchestrator.process(message=msg, session=session)

        await session_store.add_turn(session.session_id, "assistant", response.text)

        sender = TelegramSender()
        await sender.send(chat_id=chat_id, response=response)

    except Exception as e:
        logger.error("telegram_processing_error", error=str(e), exc_info=True)
    finally:
        await db_session.close()


def _extract_telegram_message(payload: dict) -> IncomingMessage | None:
    """Parse Telegram Update — extracts first_name for personalised greetings."""
    try:
        message = payload.get("message")
        if not message:
            return None

        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        user_hash = hashlib.sha256(chat_id.encode()).hexdigest()

        # Extract user's name from Telegram
        from_user = message.get("from", {})
        first_name = from_user.get("first_name", "")

        text = message.get("text", "")
        media_type = MediaType.TEXT
        location = None

        if "location" in message:
            loc = message["location"]
            location = LocationData(
                latitude=loc.get("latitude"),
                longitude=loc.get("longitude"),
            )
            text = "[Location shared]"
            media_type = MediaType.LOCATION

        if not text and not location:
            return None

        return IncomingMessage(
            message_id=str(message.get("message_id", uuid.uuid4())),
            channel=Channel.TELEGRAM,
            user_id_hash=user_hash,
            timestamp=datetime.fromtimestamp(message.get("date", 0)),
            text=text,
            media_type=media_type,
            location_data=location,
            session_id=user_hash[:16],
            user_name=first_name or None,
        )

    except Exception as e:
        logger.error("telegram_payload_parse_error", error=str(e))
        return None
