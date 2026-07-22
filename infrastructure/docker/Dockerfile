# =============================================================================
# NACA AI HIV Chatbot — Production Dockerfile
# =============================================================================
# Multi-stage build for minimal attack surface
# Base: python:3.11-slim (Debian Bookworm)
# Final image: ~150MB with read-only root filesystem support
# =============================================================================

# ── Stage 1: Builder ─────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies into a virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# ── Stage 2: Production ─────────────────────────────────────────────────────
FROM python:3.11-slim AS production

# Security: run as non-root user
RUN groupadd -r naca && useradd -r -g naca -d /app -s /sbin/nologin naca

# Install runtime dependencies only
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
WORKDIR /app
COPY src/ ./src/
COPY config/ ./config/

# Set ownership
RUN chown -R naca:naca /app

# Switch to non-root user
USER naca

# Environment defaults
ENV NACA_ENVIRONMENT=production \
    NACA_HOST=0.0.0.0 \
    NACA_PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/v1/health || exit 1

# Expose port
EXPOSE 8000

# Start with gunicorn + uvicorn workers
CMD ["gunicorn", "src.api.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
