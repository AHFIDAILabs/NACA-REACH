"""
NACA AI Chatbot — Redis Client Manager

Manages Redis connections for session storage (Memorystore for Redis on GCP).
Sessions use a 30-minute sliding TTL as defined in Section 3.1.3.
"""

import json
from datetime import datetime

import redis.asyncio as redis
import structlog

from src.core.config import get_settings
from src.schemas.messages import SessionState, ConversationTurn, Channel, SupportedLanguage

logger = structlog.get_logger()
settings = get_settings()


class RedisManager:
    """Manages the async Redis connection pool."""

    def __init__(self):
        self.client: redis.Redis | None = None

    async def connect(self):
        self.client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            max_connections=50,
        )
        await self.client.ping()
        logger.info("redis_connected", url=settings.redis_url.split("@")[-1])

    async def disconnect(self):
        if self.client:
            await self.client.aclose()
            logger.info("redis_disconnected")


redis_manager = RedisManager()


class SessionStore:
    """
    Session management backed by Redis.
    Each session has a 30-minute sliding TTL (refreshed on every interaction).
    """

    SESSION_PREFIX = "session:"

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.ttl = settings.session_ttl_seconds

    def _key(self, session_id: str) -> str:
        return f"{self.SESSION_PREFIX}{session_id}"

    async def get_session(self, session_id: str) -> SessionState | None:
        """Retrieve a session and refresh its TTL."""
        data = await self.redis.get(self._key(session_id))
        if not data:
            return None
        # Refresh TTL on access (sliding window)
        await self.redis.expire(self._key(session_id), self.ttl)
        return SessionState.model_validate_json(data)

    async def create_session(
        self,
        session_id: str,
        channel: Channel,
        user_id_hash: str,
        language: SupportedLanguage = SupportedLanguage.ENGLISH,
    ) -> SessionState:
        """Create a new session with initial state."""
        now = datetime.utcnow()
        session = SessionState(
            session_id=session_id,
            channel=channel,
            user_id_hash=user_id_hash,
            language=language,
            conversation_history=[],
            escalation_flags=[],
            low_confidence_count=0,
            created_at=now,
            last_active=now,
        )
        await self.redis.setex(
            self._key(session_id),
            self.ttl,
            session.model_dump_json(),
        )
        logger.info("session_created", session_id=session_id, channel=channel.value)
        return session

    async def update_session(self, session: SessionState) -> None:
        """Save updated session state and refresh TTL."""
        session.last_active = datetime.utcnow()
        await self.redis.setex(
            self._key(session.session_id),
            self.ttl,
            session.model_dump_json(),
        )

    async def add_turn(
        self, session_id: str, role: str, content: str
    ) -> SessionState | None:
        """Add a conversation turn and return updated session."""
        session = await self.get_session(session_id)
        if not session:
            return None
        turn = ConversationTurn(
            role=role,
            content=content,
            timestamp=datetime.utcnow(),
        )
        session.conversation_history.append(turn)
        # Keep only last 10 turns to manage context window
        if len(session.conversation_history) > 20:
            session.conversation_history = session.conversation_history[-20:]
        await self.update_session(session)
        return session

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session (NDPA erasure support)."""
        result = await self.redis.delete(self._key(session_id))
        if result:
            logger.info("session_deleted", session_id=session_id)
        return bool(result)


def get_session_store() -> SessionStore:
    """FastAPI dependency — returns session store backed by active Redis client."""
    if not redis_manager.client:
        raise RuntimeError("Redis not connected. Call redis_manager.connect() first.")
    return SessionStore(redis_manager.client)
