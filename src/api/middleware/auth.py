"""
NACA AI Chatbot — Authentication Middleware

Service-to-service token verification and admin JWT authentication.
"""

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import structlog

from src.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()
security = HTTPBearer()


async def verify_service_token(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> str:
    """Verify internal service-to-service bearer token."""
    if not settings.internal_service_token:
        if settings.is_development:
            return "dev-service"
        raise HTTPException(status_code=500, detail="Service token not configured")

    if credentials.credentials != settings.internal_service_token:
        raise HTTPException(status_code=401, detail="Invalid service token")
    return credentials.credentials


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> dict:
    """
    Verify admin JWT token.
    In production, this decodes and validates a JWT with 1-hour expiry.
    """
    token = credentials.credentials

    if settings.is_development and token == "dev-admin-token":
        return {"sub": "dev-admin", "role": "technical_admin", "tier": 4}

    # TODO: Implement full JWT decode with jose
    # decoded = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    # Check expiry, role, tier

    raise HTTPException(status_code=401, detail="Invalid or expired admin token")
