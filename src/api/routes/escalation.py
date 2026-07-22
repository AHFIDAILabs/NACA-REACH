"""
NACA AI Chatbot — Escalation API (Section 3.5)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.database import get_db
from src.schemas.messages import EscalationRequest
from src.services.escalation.escalation_service import EscalationService

logger = structlog.get_logger()
router = APIRouter()


@router.post("/escalate", response_model=dict, status_code=201)
async def trigger_escalation(
    request: EscalationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Manually trigger an escalation for a session."""
    service = EscalationService(db)
    ticket = await service.create_ticket(request)
    return {
        "ticket_id": str(ticket.ticket_id),
        "status": ticket.status,
        "priority": ticket.priority,
    }
