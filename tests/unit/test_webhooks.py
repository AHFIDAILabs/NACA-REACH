"""
NACA AI Chatbot — Unit Tests for Webhook Payload Parsing

Tests Twilio WhatsApp and Telegram webhook message extraction.
"""

import pytest
from src.api.routes.webhooks import _extract_twilio_message, _extract_telegram_message
from src.schemas.messages import Channel, MediaType


class TestTwilioWhatsAppParsing:

    def test_parse_text_message(self):
        form_data = {
            "MessageSid": "SM1234567890",
            "From": "whatsapp:+2348012345678",
            "To": "whatsapp:+14155238886",
            "Body": "Where can I get tested for HIV?",
        }
        msg = _extract_twilio_message(form_data)
        assert msg is not None
        assert msg.channel == Channel.WHATSAPP
        assert msg.text == "Where can I get tested for HIV?"
        assert msg.media_type == MediaType.TEXT
        # Phone number is hashed, not stored raw
        assert "2348012345678" not in msg.user_id_hash
        assert len(msg.user_id_hash) == 64  # SHA-256 hex

    def test_parse_location_message(self):
        form_data = {
            "MessageSid": "SM9876543210",
            "From": "whatsapp:+2348012345678",
            "Body": "",
            "Latitude": "6.5244",
            "Longitude": "3.3792",
        }
        msg = _extract_twilio_message(form_data)
        assert msg is not None
        assert msg.media_type == MediaType.LOCATION
        assert msg.location_data.latitude == 6.5244
        assert msg.location_data.longitude == 3.3792

    def test_parse_message_with_location_and_text(self):
        form_data = {
            "MessageSid": "SM1111111111",
            "From": "whatsapp:+2348012345678",
            "Body": "Find clinics here",
            "Latitude": "9.0579",
            "Longitude": "7.4951",
        }
        msg = _extract_twilio_message(form_data)
        assert msg is not None
        assert msg.text == "Find clinics here"
        assert msg.location_data is not None

    def test_strips_whatsapp_prefix_for_hashing(self):
        form_data = {
            "MessageSid": "SM2222222222",
            "From": "whatsapp:+2348012345678",
            "Body": "Hello",
        }
        msg = _extract_twilio_message(form_data)
        # Same number without prefix should produce same hash
        import hashlib
        expected_hash = hashlib.sha256("+2348012345678".encode()).hexdigest()
        assert msg.user_id_hash == expected_hash

    def test_empty_body_no_location_returns_none(self):
        form_data = {
            "MessageSid": "SM3333333333",
            "From": "whatsapp:+2348012345678",
            "Body": "",
        }
        msg = _extract_twilio_message(form_data)
        assert msg is None

    def test_no_from_returns_none(self):
        form_data = {"Body": "Hello", "MessageSid": "SM444"}
        msg = _extract_twilio_message(form_data)
        assert msg is None

    def test_message_sid_used_as_id(self):
        form_data = {
            "MessageSid": "SM5555555555",
            "From": "whatsapp:+2348099999999",
            "Body": "Test",
        }
        msg = _extract_twilio_message(form_data)
        assert msg.message_id == "SM5555555555"


class TestTelegramPayloadParsing:

    def test_parse_text_message(self):
        payload = {
            "update_id": 123456,
            "message": {
                "message_id": 42,
                "chat": {"id": 987654321, "type": "private"},
                "date": 1713520000,
                "text": "How do I protect myself from HIV?",
            },
        }
        msg = _extract_telegram_message(payload)
        assert msg is not None
        assert msg.channel == Channel.TELEGRAM
        assert msg.text == "How do I protect myself from HIV?"
        assert len(msg.user_id_hash) == 64

    def test_parse_location_message(self):
        payload = {
            "update_id": 123457,
            "message": {
                "message_id": 43,
                "chat": {"id": 987654321, "type": "private"},
                "date": 1713520000,
                "location": {"latitude": 9.0579, "longitude": 7.4951},
            },
        }
        msg = _extract_telegram_message(payload)
        assert msg is not None
        assert msg.media_type == MediaType.LOCATION
        assert msg.location_data.latitude == 9.0579

    def test_parse_command(self):
        payload = {
            "update_id": 123458,
            "message": {
                "message_id": 44,
                "chat": {"id": 987654321, "type": "private"},
                "date": 1713520000,
                "text": "/start",
            },
        }
        msg = _extract_telegram_message(payload)
        assert msg is not None
        assert msg.text == "/start"

    def test_no_message_returns_none(self):
        payload = {"update_id": 123459, "callback_query": {"data": "some_callback"}}
        msg = _extract_telegram_message(payload)
        assert msg is None
