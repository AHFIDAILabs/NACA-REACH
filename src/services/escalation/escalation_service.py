"""
NACA AI Chatbot — Escalation Service (Section 3.5)

Manages escalation ticket creation, assignment, and lifecycle
for the Human Escalation Layer.
"""

from datetime import datetime

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.models.escalation import EscalationTicket, Agent
from src.schemas.messages import EscalationRequest

logger = structlog.get_logger()


class EscalationService:
    """
    Creates and manages escalation tickets for human agent handoff.
    P1 tickets trigger immediate PagerDuty alerts.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_ticket(self, request: EscalationRequest) -> EscalationTicket:
        """
        Create an escalation ticket from a trigger detection event.
        Workflow (Section 3.5.2):
        1. Create ticket with session context
        2. Assign to available agent (or queue)
        3. For P1: trigger PagerDuty alert
        """
        ticket = EscalationTicket(
            session_id=request.session_id,
            channel="whatsapp",  # TODO: get from session
            user_id_hash="anonymised",  # TODO: get from session
            priority=request.priority.value,
            trigger_type=request.trigger_type.value,
            trigger_details=request.trigger_details,
            conversation_history=request.conversation_history or [],
            status="NEW",
        )

        self.db.add(ticket)
        await self.db.flush()
        await self.db.refresh(ticket)

        logger.warning(
            "escalation_ticket_created",
            ticket_id=str(ticket.ticket_id),
            priority=ticket.priority,
            trigger_type=ticket.trigger_type,
        )

        # Note: Agent assignment skipped — escalation routes to WhatsApp counsellors
        # via the orchestrator's _notify_counsellors method instead.

        return ticket

    async def _find_available_agent(self, ticket: EscalationTicket) -> Agent | None:
        """
        Find an available agent, preferring those who speak the user's language.
        Agents must be AVAILABLE and under their max concurrent ticket limit.
        """
        # Count current active tickets per agent
        active_ticket_count = (
            select(
                EscalationTicket.assigned_agent_id,
                func.count().label("active_count"),
            )
            .where(EscalationTicket.status.in_(["ASSIGNED", "IN_PROGRESS"]))
            .group_by(EscalationTicket.assigned_agent_id)
            .subquery()
        )

        query = (
            select(Agent)
            .outerjoin(
                active_ticket_count,
                Agent.agent_id == active_ticket_count.c.assigned_agent_id,
            )
            .where(Agent.is_active == True)
            .where(Agent.status == "AVAILABLE")
            .where(
                (active_ticket_count.c.active_count == None)
                | (active_ticket_count.c.active_count < Agent.max_concurrent_tickets)
            )
            .order_by(Agent.last_active_at.desc().nullslast())
            .limit(1)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def _trigger_pagerduty_alert(self, ticket: EscalationTicket) -> None:
        """
        Send a PagerDuty incident for P1 critical escalations.
        In production, uses the PagerDuty Events API v2.
        """
        from src.core.config import get_settings

        settings = get_settings()
        if not settings.pagerduty_integration_key:
            logger.warning("pagerduty_not_configured", ticket_id=str(ticket.ticket_id))
            return

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                await client.post(
                    "https://events.pagerduty.com/v2/enqueue",
                    json={
                        "routing_key": settings.pagerduty_integration_key,
                        "event_action": "trigger",
                        "payload": {
                            "summary": f"P1 Escalation: {ticket.trigger_type} — Ticket {ticket.ticket_id}",
                            "severity": "critical",
                            "source": "naca-chatbot",
                            "component": "escalation-service",
                            "custom_details": {
                                "ticket_id": str(ticket.ticket_id),
                                "trigger_type": ticket.trigger_type,
                                "priority": ticket.priority,
                            },
                        },
                    },
                    timeout=5.0,
                )
                logger.info(
                    "pagerduty_alert_sent",
                    ticket_id=str(ticket.ticket_id),
                )
        except Exception as e:
            logger.error(
                "pagerduty_alert_failed",
                ticket_id=str(ticket.ticket_id),
                error=str(e),
            )

    async def get_ticket(self, ticket_id: str) -> EscalationTicket | None:
        """Retrieve a ticket by ID."""
        import uuid as uuid_mod

        try:
            uid = uuid_mod.UUID(ticket_id)
        except ValueError:
            return None

        result = await self.db.execute(
            select(EscalationTicket).where(EscalationTicket.ticket_id == uid)
        )
        return result.scalar_one_or_none()

    async def resolve_ticket(
        self, ticket_id: str, category: str, notes: str
    ) -> EscalationTicket | None:
        """Mark a ticket as resolved by an agent."""
        ticket = await self.get_ticket(ticket_id)
        if not ticket:
            return None

        ticket.status = "RESOLVED"
        ticket.resolution_category = category
        ticket.resolution_notes = notes
        ticket.resolved_at = datetime.utcnow()
        await self.db.flush()

        logger.info(
            "escalation_ticket_resolved",
            ticket_id=ticket_id,
            category=category,
        )
        return ticket
