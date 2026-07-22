"""
NACA AI Chatbot — Message Processing API (Section 8.1)

Internal endpoint called by the Channel Abstraction Layer to process
a normalised message through the full AI pipeline.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.config import get_settings
from src.core.database import get_db
from src.core.redis_client import get_session_store, SessionStore
from src.schemas.messages import (
    IncomingMessage,
    BotResponse,
    EscalationResponse,
    SupportedLanguage,
)
from src.services.ai.orchestrator import AIOrchestrator

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()


@router.post("/message", response_model=BotResponse | EscalationResponse)
async def process_message(
    message: IncomingMessage,
    db: AsyncSession = Depends(get_db),
    session_store: SessionStore = Depends(get_session_store),
):
    """
    Process an incoming user message through the full AI pipeline:
    1. Resolve or create session
    2. Detect language
    3. Translate to English (if needed)
    4. NLU: intent, entities, sentiment
    5. Check escalation triggers
    6. Agentic RAG retrieval + LLM generation
    7. Safety check
    8. Translate response back (if needed)
    9. Return response
    """
    # ── 1. Session resolution ──
    session = await session_store.get_session(message.session_id or message.user_id_hash[:16])
    if not session:
        session = await session_store.create_session(
            session_id=message.session_id or message.user_id_hash[:16],
            channel=message.channel,
            user_id_hash=message.user_id_hash,
            language=message.language_hint or SupportedLanguage.ENGLISH,
        )

    # Add user message to conversation history
    await session_store.add_turn(session.session_id, "user", message.text)

    # ── 2–9. Run through AI Orchestrator ──
    orchestrator = AIOrchestrator(db=db, session_store=session_store)
    response = await orchestrator.process(message=message, session=session)

    # Add assistant response to conversation history
    if isinstance(response, BotResponse):
        await session_store.add_turn(session.session_id, "assistant", response.text)

    return response


@router.get("/session/{session_id}")
async def get_session(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
):
    """Retrieve current session state and conversation history."""
    session = await session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    return session


@router.delete("/session/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    session_store: SessionStore = Depends(get_session_store),
):
    """Terminate and purge a user session (NDPA erasure support)."""
    deleted = await session_store.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
