"""
NACA AI HIV Chatbot — FastAPI Application Entry Point

This is the main application that receives webhook messages from WhatsApp
and Telegram, processes them through the AI pipeline, and returns responses.
"""

import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.core.database import db_manager
from src.core.redis_client import redis_manager
from src.api.routes import health, messages, webhooks, referrals, escalation, admin, agent_console

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle events."""
    logger.info(
        "starting_application",
        environment=settings.environment.value,
        version=settings.api_version,
    )
    await db_manager.connect()
    await redis_manager.connect()
    logger.info("all_connections_established")

    yield

    logger.info("shutting_down_application")
    from src.services.analytics.event_emitter import flush_remaining
    await flush_remaining()
    await redis_manager.disconnect()
    await db_manager.disconnect()
    logger.info("all_connections_closed")


app = FastAPI(
    title=settings.app_name,
    version=settings.api_version,
    description="AI-Powered HIV Engagement Chatbot for NACA Nigeria",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# ── Middleware ───────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """Log every request with latency tracking."""
    start_time = time.time()
    response = await call_next(request)
    latency_ms = int((time.time() - start_time) * 1000)

    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=latency_ms,
    )
    response.headers["X-Response-Time-Ms"] = str(latency_ms)
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all — never expose internals."""
    logger.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal error occurred. Please try again."},
    )


# ── Routes ───────────────────────────────────────────────────────────────────

app.include_router(health.router, prefix="/v1", tags=["Health"])
app.include_router(webhooks.router, prefix="/v1/webhooks", tags=["Webhooks"])
app.include_router(messages.router, prefix="/v1", tags=["Messages"])
app.include_router(referrals.router, prefix="/v1/referral", tags=["Referrals"])
app.include_router(escalation.router, prefix="/v1", tags=["Escalation"])
app.include_router(admin.router, prefix="/v1/admin", tags=["Admin"])
app.include_router(agent_console.router, prefix="/v1/console", tags=["Agent Console"])
