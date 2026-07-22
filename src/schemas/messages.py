"""
NACA AI Chatbot — Message Schemas

Unified internal message schema for the Channel Abstraction Layer.
Normalises WhatsApp and Telegram payloads into a platform-agnostic format.
See: System Design Section 3.3.3
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# =============================================================================
# Enums
# =============================================================================

class Channel(str, Enum):
    WHATSAPP = "whatsapp"
    TELEGRAM = "telegram"


class SupportedLanguage(str, Enum):
    ENGLISH = "en"
    HAUSA = "ha"
    YORUBA = "yo"
    IGBO = "ig"
    PIDGIN = "pcm"


class MediaType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    LOCATION = "location"
    QUICK_REPLY = "quick_reply"
    LIST_REPLY = "list_reply"


class ResponseType(str, Enum):
    TEXT = "text"
    QUICK_REPLY = "quick_reply"
    LIST = "list"
    REFERRAL_CARD = "referral_card"
    ESCALATION_NOTICE = "escalation_notice"


class IntentCategory(str, Enum):
    PREVENTION = "prevention"
    TESTING = "testing"
    TREATMENT = "treatment"
    REFERRAL = "referral"
    MYTH_BUSTING = "myth_busting"
    CRISIS = "crisis"
    GENERAL_ENQUIRY = "general_enquiry"
    GREETING = "greeting"
    LANGUAGE_CHANGE = "language_change"
    OPT_OUT = "opt_out"
    ESCALATION_REQUEST = "escalation_request"
    UNKNOWN = "unknown"


class EscalationPriority(str, Enum):
    P1_CRITICAL = "P1_CRITICAL"
    P2_HIGH = "P2_HIGH"
    P3_MEDIUM = "P3_MEDIUM"


class EscalationTriggerType(str, Enum):
    CRISIS_LANGUAGE = "CRISIS_LANGUAGE"
    POSITIVE_DIAGNOSIS_REACTION = "POSITIVE_DIAGNOSIS_REACTION"
    CLINICAL_DECISION_REQUIRED = "CLINICAL_DECISION_REQUIRED"
    REPEATED_NON_RESOLUTION = "REPEATED_NON_RESOLUTION"
    EXPLICIT_REQUEST = "EXPLICIT_REQUEST"
    SAFEGUARDING_CONCERN = "SAFEGUARDING_CONCERN"


class ModelTier(str, Enum):
    SONNET = "sonnet"
    HAIKU = "haiku"


# =============================================================================
# Location
# =============================================================================

class LocationData(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    text_location: Optional[str] = None


# =============================================================================
# Incoming Message (normalised from any channel)
# =============================================================================

class IncomingMessage(BaseModel):
    """
    Unified internal message schema.
    Produced by Channel Adapters from raw WhatsApp/Telegram payloads.
    """
    message_id: str
    channel: Channel
    user_id_hash: str = Field(description="SHA-256 hash of phone number or chat ID")
    timestamp: datetime
    text: str
    language_hint: Optional[SupportedLanguage] = None
    media_type: MediaType = MediaType.TEXT
    location_data: Optional[LocationData] = None
    session_id: Optional[str] = None
    user_name: Optional[str] = Field(default=None, description="User's display name from WhatsApp/Telegram profile")
    raw_payload: Optional[dict] = Field(default=None, exclude=True)


# =============================================================================
# NLU Output
# =============================================================================

class NLUResult(BaseModel):
    """Output from the NLU Module — intent, entities, sentiment."""
    intent: IntentCategory
    intent_confidence: float = Field(ge=0.0, le=1.0)
    entities: dict = Field(default_factory=dict)
    sentiment_score: float = Field(ge=-1.0, le=1.0, description="Negative to positive")
    distress_level: float = Field(ge=0.0, le=10.0, description="0=calm, 10=extreme distress")
    detected_language: SupportedLanguage = SupportedLanguage.ENGLISH
    requires_escalation: bool = False
    escalation_trigger: Optional[EscalationTriggerType] = None
    escalation_priority: Optional[EscalationPriority] = None


# =============================================================================
# RAG Retrieval
# =============================================================================

class RetrievedChunk(BaseModel):
    """A single chunk retrieved from the knowledge base."""
    chunk_id: str
    document_id: str
    content: str
    content_domain: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    source_title: str
    source_organisation: Optional[str] = None


class RAGResult(BaseModel):
    """Output from the RAG pipeline."""
    chunks: list[RetrievedChunk]
    query_used: str
    retrieval_method: str = "hybrid"  # hybrid, vector, bm25
    average_confidence: float = Field(ge=0.0, le=1.0)


# =============================================================================
# Facility / Referral
# =============================================================================

class FacilitySummary(BaseModel):
    """Compact facility info for referral responses."""
    facility_id: str
    facility_name: str
    address: str
    phone_primary: str
    services: list[str]
    operating_hours: str
    distance_km: float


class ReferralSearchRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    text_location: Optional[str] = None
    service_type: Optional[str] = None
    radius_km: int = 25
    limit: int = 3


class ReferralSearchResponse(BaseModel):
    facilities: list[FacilitySummary]
    search_radius_km: int
    total_found: int


# =============================================================================
# Bot Response (platform-agnostic)
# =============================================================================

class QuickReplyOption(BaseModel):
    id: str
    title: str


class BotResponse(BaseModel):
    """
    Platform-agnostic response object.
    Channel Adapters convert this to WhatsApp/Telegram payload format.
    """
    response_id: str
    session_id: str
    text: str
    language: SupportedLanguage
    response_type: ResponseType = ResponseType.TEXT
    quick_replies: Optional[list[QuickReplyOption]] = None
    referral_results: Optional[list[FacilitySummary]] = None
    metadata: Optional[dict] = None


# =============================================================================
# Escalation
# =============================================================================

class EscalationRequest(BaseModel):
    session_id: str
    trigger_type: EscalationTriggerType
    priority: EscalationPriority
    trigger_details: Optional[dict] = None
    conversation_history: Optional[list[dict]] = None


class EscalationResponse(BaseModel):
    ticket_id: str
    holding_message: str
    estimated_wait_minutes: int


# =============================================================================
# Analytics Event
# =============================================================================

class AnalyticsEvent(BaseModel):
    event_type: str
    timestamp: datetime
    session_id_hash: Optional[str] = None
    channel: Optional[Channel] = None
    state: Optional[str] = None
    language: Optional[SupportedLanguage] = None
    intent: Optional[str] = None
    model_used: Optional[ModelTier] = None
    latency_ms: Optional[int] = None
    properties: Optional[dict] = None


# =============================================================================
# Session State (stored in Redis)
# =============================================================================

class ConversationTurn(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime


class SessionState(BaseModel):
    """Session data stored in Redis with 30-minute sliding TTL."""
    session_id: str
    channel: Channel
    user_id_hash: str
    language: SupportedLanguage = SupportedLanguage.ENGLISH
    detected_language: Optional[SupportedLanguage] = None
    conversation_history: list[ConversationTurn] = Field(default_factory=list)
    escalation_flags: list[str] = Field(default_factory=list)
    referral_state: Optional[dict] = None
    low_confidence_count: int = 0
    created_at: datetime
    last_active: datetime


# =============================================================================
# Health Check
# =============================================================================

class ComponentHealth(BaseModel):
    database: str = "unknown"
    redis: str = "unknown"
    vector_db: str = "unknown"
    llm_api: str = "unknown"


class HealthStatus(BaseModel):
    status: str  # healthy, degraded, unhealthy
    version: str
    uptime_seconds: int
    components: ComponentHealth
