"""
NACA AI Chatbot — Escalation Models (Section 3.5)

Escalation tickets and agent management for the Human Escalation Layer.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text, Boolean, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base


class Agent(Base):
    __tablename__ = "agents"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="agent", nullable=False)
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=["en"], nullable=False
    )
    status: Mapped[str] = mapped_column(
        SQLEnum("AVAILABLE", "BUSY", "OFFLINE", "ON_BREAK", name="agent_status", create_type=False),
        default="OFFLINE",
        nullable=False,
    )
    max_concurrent_tickets: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    tickets: Mapped[list["EscalationTicket"]] = relationship(back_populates="agent")


class EscalationTicket(Base):
    __tablename__ = "escalation_tickets"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(
        SQLEnum("whatsapp", "telegram", name="messaging_channel", create_type=False),
        nullable=False,
    )
    user_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[str] = mapped_column(
        SQLEnum("P1_CRITICAL", "P2_HIGH", "P3_MEDIUM", name="escalation_priority", create_type=False),
        nullable=False,
    )
    trigger_type: Mapped[str] = mapped_column(
        SQLEnum(
            "CRISIS_LANGUAGE", "POSITIVE_DIAGNOSIS_REACTION", "CLINICAL_DECISION_REQUIRED",
            "REPEATED_NON_RESOLUTION", "EXPLICIT_REQUEST", "SAFEGUARDING_CONCERN",
            name="escalation_trigger_type", create_type=False,
        ),
        nullable=False,
    )
    trigger_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    detected_language: Mapped[str] = mapped_column(
        SQLEnum("en", "ha", "yo", "ig", "pcm", name="supported_language", create_type=False),
        default="en",
        nullable=False,
    )
    conversation_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_history: Mapped[dict] = mapped_column(JSONB, nullable=False)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.agent_id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        SQLEnum("NEW", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "CLOSED", name="ticket_status", create_type=False),
        default="NEW",
        nullable=False,
    )
    resolution_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    assigned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    agent: Mapped[Agent | None] = relationship(back_populates="tickets")
