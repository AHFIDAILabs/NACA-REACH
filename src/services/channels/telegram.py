"""
NACA AI Chatbot — Telegram Channel Sender (Section 3.3.2)

Sends response messages back to users via Telegram Bot API.
Converts platform-agnostic BotResponse objects into Telegram payloads.
"""

import httpx
import structlog

from src.core.config import get_settings
from src.schemas.messages import BotResponse, ResponseType

logger = structlog.get_logger()
settings = get_settings()


class TelegramSender:
    """Sends messages to users via Telegram Bot API."""

    def __init__(self):
        self.base_url = f"https://api.telegram.org/bot{settings.telegram_bot_token}"

    async def send(self, chat_id: str, response: BotResponse):
        """Send a BotResponse to a Telegram user."""
        if not settings.telegram_bot_token:
            logger.warning("telegram_bot_token_not_configured")
            return

        if response.response_type == ResponseType.QUICK_REPLY and response.quick_replies:
            await self._send_with_keyboard(chat_id, response)
        else:
            await self._send_text(chat_id, response)

    async def _send_text(self, chat_id: str, response: BotResponse):
        payload = {
            "chat_id": chat_id,
            "text": response.text[:4096],
            "parse_mode": "HTML",
        }
        await self._call_api("sendMessage", payload)

    async def _send_with_keyboard(self, chat_id: str, response: BotResponse):
        keyboard = []
        for opt in response.quick_replies or []:
            keyboard.append([{"text": opt.title, "callback_data": opt.id}])

        payload = {
            "chat_id": chat_id,
            "text": response.text[:4096],
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": keyboard},
        }
        await self._call_api("sendMessage", payload)

    async def send_location(self, chat_id: str, lat: float, lon: float, title: str):
        """Send a venue/location pin."""
        payload = {
            "chat_id": chat_id,
            "latitude": lat,
            "longitude": lon,
            "title": title,
        }
        await self._call_api("sendVenue", payload)

    async def _call_api(self, method: str, payload: dict):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/{method}",
                    json=payload,
                    timeout=10.0,
                )
                if resp.status_code == 200:
                    logger.info("telegram_message_sent", method=method)
                else:
                    logger.error("telegram_send_failed", status=resp.status_code, body=resp.text[:200])
        except Exception as e:
            logger.error("telegram_send_error", error=str(e))
