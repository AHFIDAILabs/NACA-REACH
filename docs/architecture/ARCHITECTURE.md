# Architecture Design Document

## NACA AI-Powered HIV Engagement Chatbot
**Version:** 1.0  
**Status:** Phase 1 — Foundation & Design  
**Last Updated:** 2026-04-19

---

## 1. System Context

The NACA AI Chatbot operates within the following system context:

### External Actors
- **End Users**: Nigerian citizens accessing HIV information via WhatsApp/Telegram
- **NACA Support Agents**: Trained human agents handling escalated conversations
- **NACA Programme Managers**: Leadership reviewing analytics and programme metrics
- **Clinical Advisory Group**: HIV clinicians validating content accuracy
- **System Administrators**: Technical staff managing infrastructure and knowledge base

### External Systems
- **WhatsApp Business Cloud API** (Meta): Primary messaging channel
- **Telegram Bot API**: Secondary messaging channel
- **Anthropic Claude API**: LLM inference (Sonnet 4.6 + Haiku 4.5)
- **Google Cloud Translation API v3**: Multilingual translation
- **Google Maps Platform**: Geocoding + Distance Matrix
- **Vertex AI**: Embeddings (text-embedding-004) + Vector Search
- **DHIS2 / NHMIS**: National health information systems (Phase 5 integration)

---

## 2. Architectural Tiers

### Tier 1 — Channel Interface Layer
Receives and dispatches messages via WhatsApp and Telegram webhooks.

### Tier 2 — Orchestration Layer
API Gateway, Message Router, Session Manager. Handles authentication, 
rate limiting, routing, and session state management.

### Tier 3 — AI & Processing Layer
LLM Engine, Agentic RAG Pipeline, NLU Module, Language Detector, 
Translation Layer. Core intelligence and reasoning.

### Tier 4 — Data & Services Layer
Knowledge Base (Vector DB), Facility Database (PostGIS), 
Session Store (Redis), Analytics Store (BigQuery).

### Tier 5 — Operations Layer
Analytics Dashboard, Admin Portal, Agent Console, 
Monitoring & Alerting stack.

---

## 3. Component Interaction Flow

```
User (WhatsApp/Telegram)
    │
    ▼
[Webhook Endpoint] ── signature verification
    │
    ▼
[API Gateway] ── rate limiting, auth
    │
    ▼
[Message Router] ── session resolution (Redis)
    │
    ▼
[Language Detector] ── identify language
    │
    ▼
[Translation Layer] ── translate to English (if needed)
    │
    ▼
[NLU Module] ── intent, entities, sentiment
    │
    ▼
[Escalation Trigger Detector] ── crisis check
    │
    ├── YES → [Escalation Service] → Agent Console
    │
    ▼ NO
[AI Orchestrator / Agentic RAG]
    ├── KnowledgeSearch (Vector DB)
    ├── FacilityLookup (PostGIS)
    ├── DrugInfoLookup
    ├── MythChecker
    └── CrisisDetector
    │
    ▼
[LLM Engine (Claude)] ── generate response
    │
    ▼
[Safety Classifier] ── content validation
    │
    ▼
[Translation Layer] ── translate to user language (if needed)
    │
    ▼
[Channel Adapter] ── format for WhatsApp/Telegram
    │
    ▼
User receives response
    │
[Analytics Event Emitter] ── stream to BigQuery
```

---

## 4. Network Architecture

### VPC Design
- **VPC**: `naca-chatbot-vpc` in `africa-south1`
- **Public Subnet**: Load balancer, Cloud Armor WAF
- **Private Subnet (App)**: GKE node pools, application pods
- **Private Subnet (Data)**: Cloud SQL, Memorystore, Vector DB
- **Cloud NAT**: Outbound internet for external API calls

### Security Boundaries
- Cloud Armor WAF on Global Load Balancer (OWASP ruleset)
- VPC Service Controls for data perimeter
- Private Google Access for GCP API calls from private subnets
- Workload Identity for pod-level GCP API access (no service account keys)

---

## 5. Data Flow Classification

| Data Type | Storage | Retention | Encryption |
|-----------|---------|-----------|------------|
| Message content (transient) | Redis | 30 min TTL | AES-256 at rest, TLS 1.3 in transit |
| Session metadata | Redis | 30 min TTL | AES-256 at rest |
| Interaction analytics (anonymised) | BigQuery | 24 months | AES-256 at rest |
| Escalation transcripts | Cloud SQL (encrypted) | 90 days | AES-256 + Cloud KMS |
| Knowledge base documents | GCS + Vector DB | Indefinite (versioned) | AES-256 at rest |
| Facility records | Cloud SQL (PostGIS) | Indefinite (audited) | AES-256 at rest |
| Audit logs | Cloud Logging → BigQuery | 12 months | Immutable, AES-256 |

---

## 6. Key Design Decisions

### 6.1 LLM Tiered Routing
- **Claude Haiku 4.5** (~70% of queries): Simple FAQs, greetings, 
  basic prevention info. $1/$5 per MTok.
- **Claude Sonnet 4.6** (~30% of queries): Complex clinical queries, 
  multi-domain reasoning, agentic RAG. $3/$15 per MTok.
- **Routing**: Intent complexity classifier determines tier before LLM call.

### 6.2 Translation Strategy
- All LLM reasoning in English for accuracy.
- Google Cloud Translation API v3 for inbound/outbound translation.
- Knowledge base stored in English; translation at response layer only.
- Hausa: configurable feature flag (direct LLM vs translation).

### 6.3 Agentic RAG over Standard RAG
- Multi-tool coordination per query (knowledge + facilities + drugs + myths).
- Iterative retrieval with confidence evaluation (max 3 retries per tool).
- Required for complex queries spanning multiple domains.

### 6.4 Data Residency
- Primary: `africa-south1` (Johannesburg) — closest GCP region.
- DR: `europe-west1` (Belgium) — activated on confirmed multi-zone failure.
- NACA Legal must confirm NDPA 2023 compliance for South Africa hosting.

---

## 7. Risk Mitigations (Architecture-Level)

| Risk | Architectural Mitigation |
|------|--------------------------|
| LLM hallucination | Faithfulness scorer validates against retrieved chunks |
| Clinical inaccuracy | Post-generation safety classifier + Clinical Advisory review |
| Prompt injection | Detection layer before LLM; system prompt hardening |
| Single point of failure | Multi-AZ deployment; stateless workers; externalised state |
| Data breach | No PII stored; SHA-256 hashing; 30-min TTL; encryption everywhere |
| WhatsApp API suspension | Telegram fallback; architecture supports SMS/USSD extension |
