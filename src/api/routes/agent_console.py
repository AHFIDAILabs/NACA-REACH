"""
NACA AI Chatbot — Agent Console API (Section 3.5.3)

Endpoints for the Agent Console web application:
- Real-time ticket queue
- Ticket assignment and management
- Agent status management
- Supervisor views
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import structlog

from src.core.database import get_db
from src.api.middleware.auth import require_admin
from src.models.escalation import EscalationTicket, Agent

logger = structlog.get_logger()
router = APIRouter()


# ── Request/Response Schemas ─────────────────────────────────────────────────

class TicketActionRequest(BaseModel):
    resolution_category: str | None = None
    resolution_notes: str | None = None


class AgentStatusUpdate(BaseModel):
    status: str  # AVAILABLE, BUSY, OFFLINE, ON_BREAK


# ── Ticket Queue ─────────────────────────────────────────────────────────────

@router.get("/tickets")
async def list_tickets(
    status: str | None = None,
    priority: str | None = None,
    limit: int = Query(default=50, le=200),
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """List escalation tickets with optional filters."""
    query = select(EscalationTicket).order_by(
        desc(EscalationTicket.created_at)
    ).limit(limit)

    if status:
        query = query.where(EscalationTicket.status == status)
    if priority:
        query = query.where(EscalationTicket.priority == priority)

    result = await db.execute(query)
    tickets = result.scalars().all()

    return [
        {
            "ticket_id": str(t.ticket_id),
            "session_id": t.session_id,
            "priority": t.priority,
            "trigger_type": t.trigger_type,
            "status": t.status,
            "detected_language": t.detected_language,
            "assigned_agent_id": str(t.assigned_agent_id) if t.assigned_agent_id else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "assigned_at": t.assigned_at.isoformat() if t.assigned_at else None,
        }
        for t in tickets
    ]


@router.get("/tickets/{ticket_id}")
async def get_ticket_detail(
    ticket_id: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Get full ticket details including conversation history."""
    from src.services.escalation.escalation_service import EscalationService
    service = EscalationService(db)
    ticket = await service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    return {
        "ticket_id": str(ticket.ticket_id),
        "session_id": ticket.session_id,
        "channel": ticket.channel,
        "priority": ticket.priority,
        "trigger_type": ticket.trigger_type,
        "trigger_details": ticket.trigger_details,
        "status": ticket.status,
        "detected_language": ticket.detected_language,
        "conversation_summary": ticket.conversation_summary,
        "conversation_history": ticket.conversation_history,
        "resolution_category": ticket.resolution_category,
        "resolution_notes": ticket.resolution_notes,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
    }


@router.post("/tickets/{ticket_id}/assign")
async def assign_ticket(
    ticket_id: str,
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Assign a ticket to a specific agent."""
    from src.services.escalation.escalation_service import EscalationService
    import uuid

    service = EscalationService(db)
    ticket = await service.get_ticket(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.assigned_agent_id = uuid.UUID(agent_id)
    ticket.assigned_at = datetime.utcnow()
    ticket.status = "ASSIGNED"
    await db.commit()

    return {"status": "assigned", "ticket_id": ticket_id, "agent_id": agent_id}


@router.post("/tickets/{ticket_id}/resolve")
async def resolve_ticket(
    ticket_id: str,
    body: TicketActionRequest,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Resolve a ticket with resolution category and notes."""
    from src.services.escalation.escalation_service import EscalationService
    service = EscalationService(db)
    ticket = await service.resolve_ticket(
        ticket_id=ticket_id,
        category=body.resolution_category or "resolved",
        notes=body.resolution_notes or "",
    )
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return {"status": "resolved", "ticket_id": ticket_id}


# ── Queue Statistics ─────────────────────────────────────────────────────────

@router.get("/queue/stats")
async def queue_stats(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Real-time queue dashboard stats."""
    # Count by status
    status_counts = await db.execute(
        select(
            EscalationTicket.status,
            func.count().label("count"),
        )
        .where(EscalationTicket.status.in_(["NEW", "ASSIGNED", "IN_PROGRESS"]))
        .group_by(EscalationTicket.status)
    )

    # Count by priority
    priority_counts = await db.execute(
        select(
            EscalationTicket.priority,
            func.count().label("count"),
        )
        .where(EscalationTicket.status.in_(["NEW", "ASSIGNED", "IN_PROGRESS"]))
        .group_by(EscalationTicket.priority)
    )

    return {
        "by_status": {r[0]: r[1] for r in status_counts.all()},
        "by_priority": {r[0]: r[1] for r in priority_counts.all()},
    }


# ── Agent Management ─────────────────────────────────────────────────────────

@router.get("/agents")
async def list_agents(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """List all agents and their current status."""
    result = await db.execute(
        select(Agent).where(Agent.is_active == True).order_by(Agent.display_name)
    )
    agents = result.scalars().all()

    return [
        {
            "agent_id": str(a.agent_id),
            "display_name": a.display_name,
            "email": a.email,
            "role": a.role,
            "status": a.status,
            "languages": a.languages,
            "last_active_at": a.last_active_at.isoformat() if a.last_active_at else None,
        }
        for a in agents
    ]


@router.put("/agents/{agent_id}/status")
async def update_agent_status(
    agent_id: str,
    body: AgentStatusUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Update an agent's availability status."""
    import uuid as uuid_mod
    result = await db.execute(
        select(Agent).where(Agent.agent_id == uuid_mod.UUID(agent_id))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent.status = body.status
    agent.last_active_at = datetime.utcnow()
    await db.commit()

    return {"agent_id": agent_id, "status": body.status}
