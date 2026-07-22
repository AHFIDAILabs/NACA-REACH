"""
Health check endpoint — Section 8.1
"""

import time

from fastapi import APIRouter
from src.core.config import get_settings
from src.schemas.messages import HealthStatus, ComponentHealth

router = APIRouter()
settings = get_settings()
_start_time = time.time()


@router.get("/health", response_model=HealthStatus)
async def health_check():
    """
    Returns system health status including all component checks.
    Used by GKE liveness/readiness probes and Cloud Load Balancer.
    """
    components = ComponentHealth(
        database="up",   # TODO: actual ping check
        redis="up",      # TODO: actual ping check
        vector_db="up",  # TODO: actual ping check
        llm_api="up",    # TODO: actual ping check
    )

    all_up = all(
        v == "up"
        for v in [components.database, components.redis, components.vector_db, components.llm_api]
    )

    return HealthStatus(
        status="healthy" if all_up else "degraded",
        version=settings.api_version,
        uptime_seconds=int(time.time() - _start_time),
        components=components,
    )
