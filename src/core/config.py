"""
NACA AI Chatbot — Application Configuration

All settings are loaded from environment variables or GCP Secret Manager.
No secrets are hardcoded or stored in config files.
"""

from enum import Enum
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    In GKE, secrets are injected via Workload Identity + Secret Manager.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_prefix="NACA_",
    )

    # ── Application ──────────────────────────────────────────────────────
    app_name: str = "NACA AI HIV Chatbot"
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    log_level: LogLevel = LogLevel.INFO
    api_version: str = "v1"
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4

    # ── Database (Cloud SQL for PostgreSQL) ──────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://naca:naca_dev@localhost:5432/naca_chatbot",
        description="Async PostgreSQL connection string",
    )
    database_pool_size: int = 20
    database_max_overflow: int = 10
    database_pool_timeout: int = 30

    # ── Redis (Memorystore) ──────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    session_ttl_seconds: int = 1800  # 30 minutes

    # ── Anthropic Claude API ─────────────────────────────────────────────
    anthropic_api_key: str = ""
    claude_sonnet_model: str = "claude-sonnet-4-6"
    claude_haiku_model: str = "claude-haiku-4-5-20251001"
    llm_temperature: float = 0.3
    llm_max_output_tokens: int = 800
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 3

    # ── Google Cloud ─────────────────────────────────────────────────────
    gcp_project_id: str = ""
    gcp_region: str = "africa-south1"

    # ── Google Cloud Translation ─────────────────────────────────────────
    translation_enabled: bool = True
    hausa_direct_llm: bool = False  # Feature flag: Hausa via LLM vs translation

    # ── Vertex AI Embeddings ─────────────────────────────────────────────
    embedding_model: str = "text-embedding-004"
    embedding_dimensions: int = 768

    # ── Vector Database ──────────────────────────────────────────────────
    vector_db_type: str = "qdrant"  # "qdrant" or "vertex_ai"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "naca_knowledge_base"
    retrieval_top_k: int = 5

    # ── Twilio WhatsApp Integration ───────────────────────────────────────
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_number: str = ""  # e.g. "whatsapp:+14155238886" (sandbox) or your own number

    # ── Telegram Bot API ─────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""

    # ── Geospatial / Google Maps ─────────────────────────────────────────
    google_maps_api_key: str = ""
    referral_default_radius_km: int = 25
    referral_max_radius_km: int = 100
    referral_default_limit: int = 3

    # ── Escalation ───────────────────────────────────────────────────────
    escalation_p1_sla_minutes: int = 5
    escalation_p2_sla_minutes: int = 30
    escalation_p3_sla_minutes: int = 120
    pagerduty_integration_key: str = ""
    # Counsellor WhatsApp numbers for human handoff (comma-separated)
    # Format: whatsapp:+234XXXXXXXXXX
    counsellor_whatsapp_numbers: str = ""  # e.g. "whatsapp:+2348012345678,whatsapp:+2348098765432"
    counsellor_display_name: str = "NACA Support Counsellor"

    # ── Security ─────────────────────────────────────────────────────────
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    internal_service_token: str = ""  # Service-to-service auth
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── Rate Limiting ────────────────────────────────────────────────────
    rate_limit_per_user_per_minute: int = 20
    rate_limit_global_per_second: int = 500

    # ── Analytics (BigQuery) ─────────────────────────────────────────────
    bigquery_dataset: str = "naca_chatbot_analytics"
    bigquery_events_table: str = "interaction_events"

    # ── Monitoring ───────────────────────────────────────────────────────
    enable_metrics: bool = True
    metrics_port: int = 9090

    @field_validator("environment", mode="before")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        return v.lower()

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT


@lru_cache()
def get_settings() -> Settings:
    """Cached settings instance — loaded once per process."""
    return Settings()
