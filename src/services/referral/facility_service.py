"""
NACA AI Chatbot — Facility Service

Geospatial facility search using PostGIS for the Referral System.
Matches users to nearest HIV service facilities based on location.
"""

import uuid

from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_SetSRID, ST_MakePoint
from sqlalchemy import select, cast, Float, String, text, func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from src.core.config import get_settings
from src.models.facility import Facility
from src.schemas.messages import (
    FacilitySummary,
    ReferralSearchResponse,
)

logger = structlog.get_logger()
settings = get_settings()


class FacilityService:
    """
    Handles facility search, retrieval, and management.
    Uses PostGIS spatial queries for nearest-facility matching.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_nearest(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        text_location: str | None = None,
        service_type: str | None = None,
        radius_km: int = 25,
        limit: int = 3,
    ) -> ReferralSearchResponse:
        """
        Find nearest facilities using the referral matching algorithm (Section 3.4.3):
        1. Parse location to coordinates
        2. PostGIS query within radius
        3. Filter by service type and accreditation
        4. Rank by distance (Haversine)
        5. Return top-N results
        """
        # If text location provided without coordinates, geocode it
        if not latitude or not longitude:
            if text_location:
                coords = await self._geocode(text_location)
                if coords:
                    latitude, longitude = coords
                else:
                    return ReferralSearchResponse(
                        facilities=[],
                        search_radius_km=radius_km,
                        total_found=0,
                    )
            else:
                return ReferralSearchResponse(
                    facilities=[],
                    search_radius_km=radius_km,
                    total_found=0,
                )

        # Build PostGIS query
        user_point = func.ST_SetSRID(
            func.ST_MakePoint(longitude, latitude), 4326
        )
        distance_m = func.ST_Distance(
            Facility.location,
            cast(user_point, type_=Facility.location.type),
        )
        distance_km_col = (distance_m / 1000.0).label("distance_km")

        query = (
            select(Facility, distance_km_col)
            .where(cast(Facility.accreditation_status, String) == "Active")
            .where(
                func.ST_DWithin(
                    Facility.location,
                    cast(user_point, type_=Facility.location.type),
                    radius_km * 1000,  # meters
                )
            )
        )

        # Filter by service type if specified — cast to service_type ENUM
        if service_type:
            query = query.where(
                text("CAST(:stype AS service_type) = ANY(facilities.services)").bindparams(stype=service_type)
            )

        query = query.order_by(distance_km_col).limit(limit)

        result = await self.db.execute(query)
        rows = result.all()

        facilities = []
        for row in rows:
            facility = row[0]
            dist = round(float(row[1]), 2)
            facilities.append(
                FacilitySummary(
                    facility_id=str(facility.facility_id),
                    facility_name=facility.facility_name,
                    address=facility.address,
                    phone_primary=facility.phone_primary,
                    services=facility.services,
                    operating_hours=facility.operating_hours,
                    distance_km=dist,
                )
            )

        logger.info(
            "referral_search_completed",
            latitude=latitude,
            longitude=longitude,
            service_type=service_type,
            radius_km=radius_km,
            results_count=len(facilities),
        )

        return ReferralSearchResponse(
            facilities=facilities,
            search_radius_km=radius_km,
            total_found=len(facilities),
        )

    async def get_by_id(self, facility_id: str) -> Facility | None:
        """Get a single facility by ID."""
        try:
            uid = uuid.UUID(facility_id)
        except ValueError:
            return None

        result = await self.db.execute(
            select(Facility).where(Facility.facility_id == uid)
        )
        return result.scalar_one_or_none()

    async def update(self, facility_id: str, data: dict) -> Facility | None:
        """Update a facility record."""
        facility = await self.get_by_id(facility_id)
        if not facility:
            return None

        for key, value in data.items():
            if hasattr(facility, key) and value is not None:
                setattr(facility, key, value)

        # Update PostGIS location if coordinates changed
        if "latitude" in data and "longitude" in data:
            facility.location = f"SRID=4326;POINT({data['longitude']} {data['latitude']})"

        await self.db.flush()
        return facility

    async def _geocode(self, text_location: str) -> tuple[float, float] | None:
        """
        Geocode a text location to coordinates using Google Maps Geocoding API.
        Adds 'Nigeria' to the query to scope results.
        """
        import httpx

        api_key = settings.google_maps_api_key
        if not api_key:
            logger.warning("geocoding_no_api_key")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://maps.googleapis.com/maps/api/geocode/json",
                    params={
                        "address": f"{text_location}, Nigeria",
                        "key": api_key,
                        "components": "country:NG",
                    },
                    timeout=5.0,
                )
                data = response.json()

                if data.get("status") == "OK" and data.get("results"):
                    location = data["results"][0]["geometry"]["location"]
                    logger.info(
                        "geocode_success",
                        input=text_location,
                        lat=location["lat"],
                        lng=location["lng"],
                    )
                    return (location["lat"], location["lng"])

                logger.warning("geocode_no_results", input=text_location, status=data.get("status"))
                return None

        except Exception as e:
            logger.error("geocode_failed", input=text_location, error=str(e))
            return None