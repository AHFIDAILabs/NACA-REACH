"""
Facility Search Service — Geospatial referral matching.

Uses PostGIS spatial queries to find nearest HIV service facilities.
See: System Design for referral matching algorithm details.
"""

import uuid
from typing import Optional

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.schemas.messages import (
    FacilitySummary,
    ReferralSearchRequest,
    ReferralSearchResponse,
)

logger = structlog.get_logger()
settings = get_settings()


class FacilitySearchService:
    """
    Service for searching and managing facility records.
    Uses the PostGIS find_nearest_facilities() function.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, request: ReferralSearchRequest) -> ReferralSearchResponse:
        """
        Search for nearest facilities using the referral matching algorithm.

        Supports three location methods:
        1. GPS coordinates (latitude/longitude)
        2. Text location → geocoded to coordinates
        3. Interactive menu (state/LGA selection) — handled upstream
        """
        latitude = request.latitude
        longitude = request.longitude

        # If text location provided, geocode it
        if not latitude and request.text_location:
            coords = await self._geocode_location(request.text_location)
            if coords:
                latitude, longitude = coords
            else:
                return ReferralSearchResponse(
                    facilities=[],
                    search_radius_km=request.radius_km,
                    total_found=0,
                )

        if not latitude or not longitude:
            return ReferralSearchResponse(
                facilities=[],
                search_radius_km=request.radius_km,
                total_found=0,
            )

        # Query PostGIS using the stored function
        query = text("""
            SELECT * FROM find_nearest_facilities(
                :latitude, :longitude, :service_filter, :radius_km, :limit
            )
        """)

        result = await self.db.execute(
            query,
            {
                "latitude": latitude,
                "longitude": longitude,
                "service_filter": request.service_type,
                "radius_km": request.radius_km,
                "limit": request.limit,
            },
        )

        rows = result.fetchall()

        # If no results found, expand radius
        if not rows and request.radius_km < settings.referral_max_radius_km:
            expanded_radius = min(request.radius_km * 2, settings.referral_max_radius_km)
            logger.info(
                "expanding_search_radius",
                original=request.radius_km,
                expanded=expanded_radius,
            )
            result = await self.db.execute(
                query,
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "service_filter": request.service_type,
                    "radius_km": expanded_radius,
                    "limit": request.limit,
                },
            )
            rows = result.fetchall()

        facilities = [
            FacilitySummary(
                facility_id=str(row.facility_id),
                facility_name=row.facility_name,
                address=row.address,
                phone_primary=row.phone_primary,
                services=[s.value if hasattr(s, "value") else s for s in row.services],
                operating_hours=row.operating_hours,
                distance_km=round(row.distance_km, 1),
            )
            for row in rows
        ]

        logger.info(
            "facility_search_complete",
            latitude=latitude,
            longitude=longitude,
            radius_km=request.radius_km,
            results=len(facilities),
        )

        return ReferralSearchResponse(
            facilities=facilities,
            search_radius_km=request.radius_km,
            total_found=len(facilities),
        )

    async def get_by_id(self, facility_id: str) -> Optional[dict]:
        """Get full facility details by ID."""
        query = text("""
            SELECT facility_id, facility_name, state, lga, address,
                   latitude, longitude, phone_primary, phone_secondary,
                   email, services, operating_days, operating_hours,
                   accepts_walk_in, accreditation_status, last_verified_date,
                   data_source
            FROM facilities
            WHERE facility_id = :facility_id
        """)
        result = await self.db.execute(query, {"facility_id": facility_id})
        row = result.fetchone()

        if not row:
            return None

        return {
            "facility_id": str(row.facility_id),
            "facility_name": row.facility_name,
            "state": row.state,
            "lga": row.lga,
            "address": row.address,
            "latitude": float(row.latitude),
            "longitude": float(row.longitude),
            "phone_primary": row.phone_primary,
            "phone_secondary": row.phone_secondary,
            "email": row.email,
            "services": [s.value if hasattr(s, "value") else s for s in row.services],
            "operating_days": row.operating_days,
            "operating_hours": row.operating_hours,
            "accepts_walk_in": row.accepts_walk_in,
            "accreditation_status": row.accreditation_status,
            "last_verified_date": str(row.last_verified_date),
            "data_source": row.data_source,
        }

    async def update(self, facility_id: str, update_data: dict) -> dict:
        """Update a facility record and log the change."""
        # Log the change for audit
        await self.db.execute(
            text("""
                INSERT INTO facility_change_log
                    (facility_id, changed_by, change_type, new_values)
                VALUES (:facility_id, :changed_by, 'update', :new_values::jsonb)
            """),
            {
                "facility_id": facility_id,
                "changed_by": update_data.pop("changed_by", str(uuid.uuid4())),
                "new_values": str(update_data),
            },
        )

        # Build dynamic UPDATE query
        set_clauses = []
        params = {"facility_id": facility_id}
        for key, value in update_data.items():
            set_clauses.append(f"{key} = :{key}")
            params[key] = value

        if set_clauses:
            query = text(
                f"UPDATE facilities SET {', '.join(set_clauses)}, "
                f"updated_at = NOW() WHERE facility_id = :facility_id"
            )
            await self.db.execute(query, params)

        return await self.get_by_id(facility_id)

    async def start_bulk_import(self, csv_content: bytes, data_source: str) -> str:
        """Start a bulk import job. Returns job ID for tracking."""
        job_id = str(uuid.uuid4())
        logger.info("bulk_import_started", job_id=job_id, data_source=data_source)
        # TODO: Queue background job for CSV parsing and upsert
        return job_id

    async def _geocode_location(self, text_location: str) -> Optional[tuple[float, float]]:
        """
        Geocode a text location to coordinates using Google Maps API.
        Falls back to state-level coordinates if geocoding fails.
        """
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={
                        "address": f"{text_location}, Nigeria",
                        "key": settings.google_maps_api_key,
                    },
                )

                data = response.json()
                if data["status"] == "OK" and data["results"]:
                    loc = data["results"][0]["geometry"]["location"]
                    return loc["lat"], loc["lng"]

        except Exception as e:
            logger.error("geocoding_failed", location=text_location, error=str(e))

        # Fallback: try matching to known state coordinates
        return self._state_coordinate_fallback(text_location)

    def _state_coordinate_fallback(self, text: str) -> Optional[tuple[float, float]]:
        """Approximate coordinates for Nigerian states."""
        state_coords = {
            "lagos": (6.5244, 3.3792),
            "abuja": (9.0579, 7.4951),
            "fct": (9.0579, 7.4951),
            "kano": (12.0022, 8.5920),
            "rivers": (4.8156, 7.0498),
            "oyo": (7.3775, 3.9470),
            "benue": (7.7322, 8.5391),
            "nasarawa": (8.5380, 8.3230),
            "kaduna": (10.5105, 7.4165),
            "enugu": (6.4584, 7.5464),
            "delta": (5.8904, 5.6804),
            "edo": (6.3350, 5.6037),
        }

        text_lower = text.lower().strip()
        for state, coords in state_coords.items():
            if state in text_lower:
                return coords
        return None
