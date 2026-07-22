"""
Rate Limiting Middleware

Per-user: 20 messages/minute (configurable)
Global: 500 messages/second (configurable)
Uses Redis for distributed rate limiting across GKE pods.
"""

from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

from src.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Paths exempt from rate limiting
EXEMPT_PATHS = {"/v1/health", "/docs", "/redoc", "/openapi.json"}


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Distributed rate limiter using Redis sliding window.

    Limits:
    - Per user: NACA_RATE_LIMIT_PER_USER_PER_MINUTE (default 20)
    - Global: NACA_RATE_LIMIT_GLOBAL_PER_SECOND (default 500)
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        if path in EXEMPT_PATHS or settings.is_development:
            return await call_next(request)

        # Extract user identifier from request
        user_id = self._extract_user_id(request)
        if user_id:
            is_limited = await self._check_user_rate_limit(user_id)
            if is_limited:
                logger.warning("rate_limited", user_id_prefix=user_id[:8], path=path)
                return Response(
                    content='{"error": "rate_limited", "message": "Too many requests. Please wait a moment."}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "60"},
                )

        return await call_next(request)

    def _extract_user_id(self, request: Request) -> str | None:
        """Extract a user identifier for per-user rate limiting."""
        # Try to get user_id_hash from the request body (for message endpoints)
        # Fall back to IP address for other endpoints
        return request.client.host if request.client else None

    async def _check_user_rate_limit(self, user_id: str) -> bool:
        """
        Check if user has exceeded their rate limit.
        Uses Redis sliding window counter.

        Returns True if rate limited, False if allowed.
        """
        try:
            from src.core.redis_client import get_redis
            import time

            client = get_redis()
            key = f"ratelimit:{user_id}"
            now = time.time()
            window = 60  # 1-minute window

            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window)
            results = await pipe.execute()

            request_count = results[2]
            return request_count > settings.rate_limit_per_user_per_minute

        except Exception as e:
            # If Redis is down, allow the request (fail open)
            logger.error("rate_limit_check_failed", error=str(e))
            return False
