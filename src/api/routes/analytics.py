"""
Analytics Routes — Event ingestion and dashboard metrics.
See: System Design Section 3.6
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.schemas.messages import AnalyticsEvent
from src.services.analytics.event_service import AnalyticsEventService

router = APIRouter()


@router.post("/events", status_code=202)
async def ingest_events(
    events: list[AnalyticsEvent],
    db: AsyncSession = Depends(get_db),
):
    """
    Ingest one or more anonymised interaction events.
    Events are buffered and streamed to BigQuery.
    """
    service = AnalyticsEventService(db)
    await service.ingest_batch(events)
    return {"accepted": len(events)}


@router.get("/analytics/summary")
async def get_analytics_summary(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    state: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Get summary metrics for the analytics dashboard.
    Supports date range filtering, state, and channel filters.
    """
    service = AnalyticsEventService(db)
    return await service.get_summary(
        start_date=start_date,
        end_date=end_date,
        state=state,
        channel=channel,
    )
