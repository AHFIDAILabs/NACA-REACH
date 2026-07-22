"""
NACA AI Chatbot — Analytics Event Emitter (Section 3.6)

Captures anonymised interaction events and streams them to BigQuery
for programme intelligence dashboards.

Events are buffered in memory and flushed in batches to reduce
API calls. In production, Pub/Sub can replace direct BigQuery writes.
"""

import asyncio
import uuid
from datetime import datetime
from collections import deque

import structlog

from src.core.config import get_settings
from src.schemas.messages import (
    AnalyticsEvent, BotResponse, IncomingMessage,
    Channel, SupportedLanguage, ModelTier,
)

logger = structlog.get_logger()
settings = get_settings()

# Buffer for batching events before BigQuery write
_event_buffer: deque[dict] = deque(maxlen=10000)
FLUSH_THRESHOLD = 100  # Flush after N events


class AnalyticsEmitter:
    """
    Emits anonymised interaction events for analytics.
    Events are buffered and written to BigQuery in batches.
    """

    @staticmethod
    def emit_message_received(message: IncomingMessage, state: str | None = None):
        """Track an incoming user message."""
        _emit({
            "event_id": str(uuid.uuid4()),
            "event_type": "message_received",
            "event_timestamp": datetime.utcnow().isoformat(),
            "session_id_hash": message.user_id_hash[:16],
            "channel": message.channel.value,
            "state": state,
            "language": message.language_hint.value if message.language_hint else None,
        })

    @staticmethod
    def emit_response_sent(
        response: BotResponse,
        intent: str | None = None,
        model_used: str | None = None,
        latency_ms: int | None = None,
        confidence: float | None = None,
    ):
        """Track an outgoing bot response."""
        _emit({
            "event_id": str(uuid.uuid4()),
            "event_type": "response_sent",
            "event_timestamp": datetime.utcnow().isoformat(),
            "session_id_hash": response.session_id[:16],
            "language": response.language.value,
            "intent": intent,
            "model_used": model_used,
            "latency_ms": latency_ms,
            "retrieval_confidence": confidence,
        })

    @staticmethod
    def emit_referral_requested(
        session_hash: str,
        channel: str,
        state: str | None,
        service_type: str | None,
        results_count: int,
    ):
        """Track a facility referral search."""
        _emit({
            "event_id": str(uuid.uuid4()),
            "event_type": "referral_requested",
            "event_timestamp": datetime.utcnow().isoformat(),
            "session_id_hash": session_hash[:16],
            "channel": channel,
            "state": state,
            "service_type_requested": service_type,
            "referral_requested": True,
        })

    @staticmethod
    def emit_escalation_triggered(
        session_hash: str,
        channel: str,
        priority: str,
        trigger_type: str,
    ):
        """Track an escalation event."""
        _emit({
            "event_id": str(uuid.uuid4()),
            "event_type": "escalation_triggered",
            "event_timestamp": datetime.utcnow().isoformat(),
            "session_id_hash": session_hash[:16],
            "channel": channel,
            "escalation_triggered": True,
            "escalation_priority": priority,
        })

    @staticmethod
    def emit_session_event(session_hash: str, channel: str, event_type: str):
        """Track session start/end."""
        _emit({
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "event_timestamp": datetime.utcnow().isoformat(),
            "session_id_hash": session_hash[:16],
            "channel": channel,
        })


def _emit(event: dict):
    """Add event to buffer and flush if threshold reached."""
    _event_buffer.append(event)
    if len(_event_buffer) >= FLUSH_THRESHOLD:
        asyncio.create_task(_flush_to_bigquery())


async def _flush_to_bigquery():
    """Write buffered events to BigQuery."""
    if not _event_buffer:
        return

    events = list(_event_buffer)
    _event_buffer.clear()

    try:
        from google.cloud import bigquery
        client = bigquery.Client(project=settings.gcp_project_id)
        table_id = f"{settings.gcp_project_id}.{settings.bigquery_dataset}.{settings.bigquery_events_table}"

        errors = client.insert_rows_json(table_id, events)
        if errors:
            logger.error("bigquery_insert_errors", errors=errors[:3])
        else:
            logger.info("bigquery_events_flushed", count=len(events))

    except Exception as e:
        logger.error("bigquery_flush_failed", error=str(e), events_lost=len(events))
        # Re-buffer events on failure (best effort)
        for event in events[:1000]:
            _event_buffer.append(event)


async def flush_remaining():
    """Flush any remaining events — called on app shutdown."""
    if _event_buffer:
        await _flush_to_bigquery()
