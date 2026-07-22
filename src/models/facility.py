"""
NACA AI Chatbot — Facility Model

Represents HIV service facilities across Nigeria for the Geospatial Referral System.
"""

import uuid
from datetime import date, datetime

from geoalchemy2 import Geography
from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Enum,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class Facility(Base):
    __tablename__ = "facilities"

    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_name: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    lga: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str] = mapped_column(
        Geography(geometry_type="POINT", srid=4326), nullable=False
    )
    latitude: Mapped[float] = mapped_column(Numeric(10, 8), nullable=False)
    longitude: Mapped[float] = mapped_column(Numeric(11, 8), nullable=False)
    phone_primary: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_secondary: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    services: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    operating_days: Mapped[str] = mapped_column(String(100), nullable=False)
    operating_hours: Mapped[str] = mapped_column(String(100), nullable=False)
    accepts_walk_in: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    accreditation_status: Mapped[str] = mapped_column(
        String(20), default="Active", nullable=False
    )
    last_verified_date: Mapped[date] = mapped_column(Date, nullable=False)
    data_source: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
