"""
NACA AI Chatbot — Admin API

Facility data management and knowledge base admin endpoints.
Protected by Admin JWT authentication.
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.database import get_db
from src.api.middleware.auth import require_admin
from src.services.referral.facility_service import FacilityService

logger = structlog.get_logger()
router = APIRouter()


@router.put("/facility/{facility_id}")
async def update_facility(
    facility_id: str,
    update_data: dict,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Update a facility record (admin only)."""
    service = FacilityService(db)
    facility = await service.update(facility_id, update_data)
    if not facility:
        raise HTTPException(status_code=404, detail="Facility not found")
    return {"status": "updated", "facility_id": facility_id}


@router.post("/facility/bulk-import", status_code=202)
async def bulk_import_facilities(
    file: UploadFile = File(...),
    data_source: str = "NACA",
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Bulk import facility data via CSV upload."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are accepted")

    # TODO: Queue the import job for async processing
    content = await file.read()
    logger.info("bulk_import_started", filename=file.filename, size=len(content))

    return {
        "status": "accepted",
        "filename": file.filename,
        "message": "Import job queued for processing.",
    }
