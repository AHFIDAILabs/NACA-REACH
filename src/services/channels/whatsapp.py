"""
NACA AI Chatbot — WhatsApp Sender via Twilio (Section 3.3.1)

Sends response messages back to WhatsApp users through Twilio's API.
Converts platform-agnostic BotResponse objects into Twilio message payloads.
"""

import httpx
import structlog
from base64 import b64encode

from src.core.config import get_settings
from src.schemas.messages import BotResponse, ResponseType

logger = structlog.get_logger()
settings = get_settings()


class WhatsAppSender:
    """Sends WhatsApp messages via Twilio API."""

    def __init__(self):
        self.account_sid = settings.twilio_account_sid
        self.auth_token = settings.twilio_auth_token
        self.from_number = settings.twilio_whatsapp_number
        self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"

    def _auth_header(self) -> dict:
        """Build Basic Auth header for Twilio API."""
        credentials = b64encode(
            f"{self.account_sid}:{self.auth_token}".encode()
        ).decode()
        return {
            "Authorization": f"Basic {credentials}",
        }

    async def send(self, to_number: str, response: BotResponse):
        """
        Send a BotResponse to a WhatsApp user via Twilio.

        Args:
            to_number: The user's WhatsApp number (e.g. "whatsapp:+2348012345678")
            response: The bot's response to send
        """
        if not self.account_sid or not self.auth_token:
            logger.warning("twilio_not_configured")
            return

        # Ensure the number has the whatsapp: prefix
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        # Build message text (include quick reply options as text if present)
        text = response.text
        if response.response_type == ResponseType.QUICK_REPLY and response.quick_replies:
            options = "\n".join(
                f"• {opt.title}" for opt in response.quick_replies
            )
            text = f"{text}\n\n{options}"

        if response.response_type == ResponseType.REFERRAL_CARD and response.referral_results:
            facilities = "\n\n".join(
                f"📍 *{f.facility_name}*\n"
                f"   {f.address}\n"
                f"   📞 {f.phone_primary}\n"
                f"   🕐 {f.operating_hours}\n"
                f"   📏 {f.distance_km:.1f} km away"
                for f in response.referral_results
            )
            text = f"{text}\n\n{facilities}"

        # Send via Twilio API
        payload = {
            "From": self.from_number,
            "To": to_number,
            "Body": text[:1600],  # Twilio WhatsApp body limit
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self.base_url,
                    data=payload,
                    headers=self._auth_header(),
                    timeout=10.0,
                )

                if resp.status_code in (200, 201):
                    resp_data = resp.json()
                    logger.info(
                        "whatsapp_message_sent",
                        sid=resp_data.get("sid", ""),
                        to=to_number[:15] + "***",
                    )
                else:
                    logger.error(
                        "whatsapp_send_failed",
                        status=resp.status_code,
                        body=resp.text[:300],
                    )

        except Exception as e:
            logger.error("whatsapp_send_error", error=str(e))
