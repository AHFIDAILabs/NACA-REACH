-- =============================================================================
-- NACA AI HIV Chatbot — Database Schema
-- PostgreSQL 15+ with PostGIS
-- =============================================================================
-- Environment: Cloud SQL for PostgreSQL (GCP)
-- Extensions: PostGIS, pgcrypto, uuid-ossp
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "postgis";

-- =============================================================================
-- ENUM TYPES
-- =============================================================================

CREATE TYPE service_type AS ENUM (
    'HTS',      -- HIV Testing Services
    'ART',      -- Antiretroviral Therapy
    'PrEP',     -- Pre-Exposure Prophylaxis
    'PEP',      -- Post-Exposure Prophylaxis
    'PMTCT',    -- Prevention of Mother-to-Child Transmission
    'VMMC',     -- Voluntary Medical Male Circumcision
    'OVC',      -- Orphans and Vulnerable Children
    'TB',       -- Tuberculosis
    'Counselling'
);

CREATE TYPE accreditation_status AS ENUM (
    'Active',
    'Suspended',
    'Inactive'
);

CREATE TYPE messaging_channel AS ENUM (
    'whatsapp',
    'telegram'
);

CREATE TYPE escalation_priority AS ENUM (
    'P1_CRITICAL',
    'P2_HIGH',
    'P3_MEDIUM'
);

CREATE TYPE escalation_trigger_type AS ENUM (
    'CRISIS_LANGUAGE',
    'POSITIVE_DIAGNOSIS_REACTION',
    'CLINICAL_DECISION_REQUIRED',
    'REPEATED_NON_RESOLUTION',
    'EXPLICIT_REQUEST',
    'SAFEGUARDING_CONCERN'
);

CREATE TYPE ticket_status AS ENUM (
    'NEW',
    'ASSIGNED',
    'IN_PROGRESS',
    'RESOLVED',
    'CLOSED'
);

CREATE TYPE agent_status AS ENUM (
    'AVAILABLE',
    'BUSY',
    'OFFLINE',
    'ON_BREAK'
);

CREATE TYPE content_domain AS ENUM (
    'PREVENTION',
    'ART_TREATMENT',
    'TESTING_SERVICES',
    'MYTH_CORRECTION',
    'CRISIS_SUPPORT',
    'FAQ',
    'DRUG_INFORMATION'
);

CREATE TYPE supported_language AS ENUM (
    'en',       -- English
    'ha',       -- Hausa
    'yo',       -- Yoruba
    'ig',       -- Igbo
    'pcm'       -- Nigerian Pidgin
);

CREATE TYPE document_status AS ENUM (
    'PENDING',
    'PROCESSING',
    'INDEXED',
    'FAILED',
    'ARCHIVED'
);

-- =============================================================================
-- 1. FACILITY DIRECTORY (Geospatial Referral System — Section 3.4.1)
-- =============================================================================

CREATE TABLE facilities (
    facility_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_name       VARCHAR(255) NOT NULL,
    state               VARCHAR(50) NOT NULL,
    lga                 VARCHAR(100) NOT NULL,
    address             TEXT NOT NULL,
    location            GEOGRAPHY(POINT, 4326) NOT NULL,  -- PostGIS point
    latitude            DECIMAL(10, 8) NOT NULL,
    longitude           DECIMAL(11, 8) NOT NULL,
    phone_primary       VARCHAR(20) NOT NULL,
    phone_secondary     VARCHAR(20),
    email               VARCHAR(255),
    services            service_type[] NOT NULL,
    operating_days      VARCHAR(100) NOT NULL,
    operating_hours     VARCHAR(100) NOT NULL,
    accepts_walk_in     BOOLEAN NOT NULL DEFAULT TRUE,
    accreditation_status accreditation_status NOT NULL DEFAULT 'Active',
    last_verified_date  DATE NOT NULL,
    data_source         VARCHAR(100) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Spatial index for geospatial queries
CREATE INDEX idx_facilities_location ON facilities USING GIST (location);
CREATE INDEX idx_facilities_state ON facilities (state);
CREATE INDEX idx_facilities_lga ON facilities (state, lga);
CREATE INDEX idx_facilities_services ON facilities USING GIN (services);
CREATE INDEX idx_facilities_accreditation ON facilities (accreditation_status);

-- =============================================================================
-- 2. AGENTS (Support Agent Management) — must be before escalation_tickets
-- =============================================================================

CREATE TABLE agents (
    agent_id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email               VARCHAR(255) UNIQUE NOT NULL,
    display_name        VARCHAR(100) NOT NULL,
    role                VARCHAR(50) NOT NULL DEFAULT 'agent',  -- agent, supervisor, admin
    languages           supported_language[] NOT NULL DEFAULT '{en}',
    status              agent_status NOT NULL DEFAULT 'OFFLINE',
    max_concurrent_tickets INT NOT NULL DEFAULT 3,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at      TIMESTAMPTZ
);

CREATE INDEX idx_agents_status ON agents (status) WHERE is_active = TRUE;
CREATE INDEX idx_agents_role ON agents (role);

-- =============================================================================
-- 3. ESCALATION TICKETS (Human Escalation Layer — Section 3.5)
-- =============================================================================

CREATE TABLE escalation_tickets (
    ticket_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          VARCHAR(128) NOT NULL,
    channel             messaging_channel NOT NULL,
    user_id_hash        VARCHAR(64) NOT NULL,  -- SHA-256 hash, no PII
    priority            escalation_priority NOT NULL,
    trigger_type        escalation_trigger_type NOT NULL,
    trigger_details     JSONB,                  -- Additional context
    detected_language   supported_language NOT NULL DEFAULT 'en',
    conversation_summary TEXT,                  -- AI-generated summary
    conversation_history JSONB NOT NULL,        -- Full transcript
    assigned_agent_id   UUID REFERENCES agents(agent_id),
    status              ticket_status NOT NULL DEFAULT 'NEW',
    resolution_category VARCHAR(100),
    resolution_notes    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_at         TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    closed_at           TIMESTAMPTZ
);

CREATE INDEX idx_tickets_status ON escalation_tickets (status);
CREATE INDEX idx_tickets_priority ON escalation_tickets (priority, status);
CREATE INDEX idx_tickets_agent ON escalation_tickets (assigned_agent_id, status);
CREATE INDEX idx_tickets_created ON escalation_tickets (created_at DESC);

-- =============================================================================
-- 4. KNOWLEDGE BASE DOCUMENTS (RAG Pipeline — Section 3.2)
-- =============================================================================

CREATE TABLE knowledge_documents (
    document_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title               VARCHAR(500) NOT NULL,
    file_name           VARCHAR(255) NOT NULL,
    file_path           TEXT NOT NULL,           -- GCS path
    file_size_bytes     BIGINT NOT NULL,
    content_domain      content_domain NOT NULL,
    source_organisation VARCHAR(255),            -- e.g., NACA, WHO, FMOH
    version             INT NOT NULL DEFAULT 1,
    status              document_status NOT NULL DEFAULT 'PENDING',
    chunk_count         INT DEFAULT 0,
    language            supported_language NOT NULL DEFAULT 'en',
    uploaded_by         UUID NOT NULL,
    approved_by         UUID,                    -- Clinical Advisory Group reviewer
    approved_at         TIMESTAMPTZ,
    processing_error    TEXT,
    metadata            JSONB,                   -- Additional flexible metadata
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_documents_domain ON knowledge_documents (content_domain);
CREATE INDEX idx_documents_status ON knowledge_documents (status);
CREATE INDEX idx_documents_version ON knowledge_documents (title, version DESC);

-- =============================================================================
-- 5. DOCUMENT CHUNKS (Vector embeddings metadata)
-- =============================================================================

CREATE TABLE document_chunks (
    chunk_id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id         UUID NOT NULL REFERENCES knowledge_documents(document_id) ON DELETE CASCADE,
    chunk_index         INT NOT NULL,
    content_text        TEXT NOT NULL,
    token_count         INT NOT NULL,
    content_domain      content_domain NOT NULL,
    language            supported_language NOT NULL DEFAULT 'en',
    vector_id           VARCHAR(255),            -- ID in Vector DB (Qdrant/Vertex)
    embedding_model     VARCHAR(100) NOT NULL DEFAULT 'text-embedding-004',
    metadata            JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_chunks_document ON document_chunks (document_id);
CREATE INDEX idx_chunks_domain ON document_chunks (content_domain);
CREATE INDEX idx_chunks_vector ON document_chunks (vector_id);

-- =============================================================================
-- 6. REFERRAL LOGS (Anonymised referral analytics)
-- =============================================================================

CREATE TABLE referral_logs (
    referral_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id_hash     VARCHAR(64) NOT NULL,     -- Anonymised
    facility_id         UUID REFERENCES facilities(facility_id),
    service_type_requested service_type NOT NULL,
    state               VARCHAR(50) NOT NULL,
    lga                 VARCHAR(100),
    search_radius_km    INT NOT NULL,
    results_count       INT NOT NULL,
    channel             messaging_channel NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_referrals_state ON referral_logs (state);
CREATE INDEX idx_referrals_service ON referral_logs (service_type_requested);
CREATE INDEX idx_referrals_created ON referral_logs (created_at DESC);

-- =============================================================================
-- 7. OPT-OUT REGISTRY (NDPA Compliance)
-- =============================================================================

CREATE TABLE opt_out_registry (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id_hash        VARCHAR(64) UNIQUE NOT NULL,  -- SHA-256 of phone/chat_id
    channel             messaging_channel NOT NULL,
    opted_out_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reason              VARCHAR(100) DEFAULT 'USER_REQUEST'
);

CREATE INDEX idx_optout_hash ON opt_out_registry (user_id_hash);

-- =============================================================================
-- 8. ADMIN USERS (Dashboard & Admin Portal)
-- =============================================================================

CREATE TABLE admin_users (
    user_id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email               VARCHAR(255) UNIQUE NOT NULL,
    display_name        VARCHAR(100) NOT NULL,
    role                VARCHAR(50) NOT NULL,  -- executive, programme_manager, operations, technical_admin
    access_tier         INT NOT NULL DEFAULT 2,  -- 1=Executive, 2=Programme, 3=Ops, 4=TechAdmin
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    mfa_enabled         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at       TIMESTAMPTZ
);

-- =============================================================================
-- 9. AUDIT LOG (Compliance & Security — immutable)
-- =============================================================================

CREATE TABLE audit_log (
    log_id              BIGSERIAL PRIMARY KEY,
    event_type          VARCHAR(100) NOT NULL,
    actor_id            UUID,
    actor_type          VARCHAR(50) NOT NULL,   -- system, agent, admin, user
    resource_type       VARCHAR(100) NOT NULL,
    resource_id         VARCHAR(255),
    action              VARCHAR(50) NOT NULL,    -- create, read, update, delete
    details             JSONB,
    ip_address          INET,
    user_agent          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_event ON audit_log (event_type);
CREATE INDEX idx_audit_actor ON audit_log (actor_id);
CREATE INDEX idx_audit_resource ON audit_log (resource_type, resource_id);
CREATE INDEX idx_audit_created ON audit_log (created_at DESC);

-- Prevent updates/deletes on audit log (immutability)
CREATE RULE audit_no_update AS ON UPDATE TO audit_log DO INSTEAD NOTHING;
CREATE RULE audit_no_delete AS ON DELETE TO audit_log DO INSTEAD NOTHING;

-- =============================================================================
-- 10. FACILITY CHANGE LOG (Data quality tracking)
-- =============================================================================

CREATE TABLE facility_change_log (
    change_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    facility_id         UUID NOT NULL REFERENCES facilities(facility_id),
    changed_by          UUID NOT NULL,
    change_type         VARCHAR(20) NOT NULL,   -- create, update, deactivate
    previous_values     JSONB,
    new_values          JSONB NOT NULL,
    change_reason       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_facility_changes ON facility_change_log (facility_id, created_at DESC);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables with updated_at
CREATE TRIGGER update_facilities_timestamp
    BEFORE UPDATE ON facilities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_agents_timestamp
    BEFORE UPDATE ON agents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_documents_timestamp
    BEFORE UPDATE ON knowledge_documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_admin_users_timestamp
    BEFORE UPDATE ON admin_users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- FACILITY SEARCH FUNCTION (Referral Matching — Section 3.4.3)
-- =============================================================================

CREATE OR REPLACE FUNCTION find_nearest_facilities(
    p_latitude DECIMAL,
    p_longitude DECIMAL,
    p_service_filter service_type DEFAULT NULL,
    p_radius_km INT DEFAULT 25,
    p_limit INT DEFAULT 3
)
RETURNS TABLE (
    facility_id UUID,
    facility_name VARCHAR(255),
    state VARCHAR(50),
    lga VARCHAR(100),
    address TEXT,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    phone_primary VARCHAR(20),
    services service_type[],
    operating_days VARCHAR(100),
    operating_hours VARCHAR(100),
    accepts_walk_in BOOLEAN,
    distance_km DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        f.facility_id,
        f.facility_name,
        f.state,
        f.lga,
        f.address,
        f.latitude,
        f.longitude,
        f.phone_primary,
        f.services,
        f.operating_days,
        f.operating_hours,
        f.accepts_walk_in,
        ST_Distance(
            f.location,
            ST_SetSRID(ST_MakePoint(p_longitude, p_latitude), 4326)::geography
        ) / 1000.0 AS distance_km
    FROM facilities f
    WHERE
        f.accreditation_status = 'Active'
        AND ST_DWithin(
            f.location,
            ST_SetSRID(ST_MakePoint(p_longitude, p_latitude), 4326)::geography,
            p_radius_km * 1000  -- Convert km to meters
        )
        AND (p_service_filter IS NULL OR p_service_filter = ANY(f.services))
    ORDER BY distance_km ASC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;