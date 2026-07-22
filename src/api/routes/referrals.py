"""
NACA AI Chatbot — Referral Service API (Section 8.2)

Geospatial facility search endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.database import get_db
from src.schemas.messages import ReferralSearchRequest, ReferralSearchResponse
from src.services.referral.facility_service import FacilityService

logger = structlog.get_logger()
router = APIRouter()


@router.post("/search", response_model=ReferralSearchResponse)
async def search_facilities(
    request: ReferralSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Search for nearest HIV service facilities by coordinates or text location.
    Uses PostGIS spatial queries with configurable radius.
    """
    service = FacilityService(db)
    results = await service.find_nearest(
        latitude=request.latitude,
        longitude=request.longitude,
        text_location=request.text_location,
        service_type=request.service_type,
        radius_km=request.radius_km,
        limit=request.limit,
    )
    return results


@router.get("/facility/{facility_id}")
async def get_facility(
    facility_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get full details for a specific facility."""
    service = FacilityService(db)
    facility = await service.get_by_id(facility_id)
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    return facility
