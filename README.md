# NACA AI-Powered HIV Engagement Chatbot

**National Agency for the Control of AIDS — Federal Republic of Nigeria**

An AI-powered conversational chatbot for HIV information, service referrals, and clinical navigation, deployed on WhatsApp and Telegram at national scale.

---

## System Overview

| Component | Description |
|-----------|-------------|
| Conversational AI Engine | Claude-powered NLU + response generation with clinical safety guardrails |
| Agentic RAG Pipeline | Multi-tool retrieval-augmented generation with knowledge base management |
| Messaging Integration | WhatsApp Business API + Telegram Bot API via unified abstraction layer |
| Geospatial Referral | PostGIS-powered facility matching across all 36 states + FCT |
| Human Escalation | Priority-based handoff to trained NACA agents with Agent Console |
| Analytics Dashboard | Real-time programme intelligence with BigQuery + Looker/React |

## Architecture

- **Cloud:** Google Cloud Platform (GCP) — primary region `africa-south1`
- **Compute:** GKE Autopilot (Kubernetes)
- **AI/LLM:** Anthropic Claude Sonnet 4.6 (complex) + Haiku 4.5 (routing)
- **Database:** Cloud SQL (PostgreSQL 15+ with PostGIS)
- **Cache:** Memorystore for Redis
- **Vector DB:** Vertex AI Vector Search / Qdrant
- **Analytics:** BigQuery + Looker Studio
- **Languages:** English, Hausa, Yoruba, Igbo, Nigerian Pidgin

## Project Structure

```
naca-hiv-chatbot/
├── src/
│   ├── api/               # FastAPI application, routes, middleware
│   │   ├── routes/         # API endpoint definitions
│   │   └── middleware/     # Auth, rate limiting, logging
│   ├── core/               # App config, settings, constants
│   ├── services/           # Business logic layer
│   │   ├── ai/             # LLM integration, orchestrator
│   │   ├── rag/            # RAG pipeline, vector search
│   │   ├── nlu/            # Intent classification, NER, sentiment
│   │   ├── translation/    # Google Cloud Translation integration
│   │   ├── referral/       # Geospatial facility matching
│   │   ├── escalation/     # Human handoff workflows
│   │   └── analytics/      # Event instrumentation
│   ├── models/             # SQLAlchemy / DB models
│   ├── schemas/            # Pydantic request/response schemas
│   ├── utils/              # Shared utilities
│   └── workers/            # Background job processors
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── infrastructure/
│   ├── terraform/          # IaC for all GCP resources
│   └── docker/             # Dockerfiles
├── docs/
│   ├── architecture/       # C4 diagrams, architecture docs
│   ├── api_contracts/      # OpenAPI specs
│   ├── schemas/            # DB schema documentation
│   └── runbooks/           # Operational runbooks
├── scripts/                # DB migrations, seed data, deployment
├── config/                 # Environment configs
└── .github/workflows/      # CI/CD pipelines
```

## Tech Stack

| Category | Technology |
|----------|------------|
| Language | Python 3.11+ |
| Framework | FastAPI |
| LLM | Anthropic Claude (Sonnet 4.6 + Haiku 4.5) |
| Embeddings | Google text-embedding-004 (Vertex AI) |
| Translation | Google Cloud Translation API v3 |
| Database | PostgreSQL 15+ with PostGIS |
| Cache | Redis 7+ |
| Vector Store | Vertex AI Vector Search / Qdrant |
| Analytics | BigQuery |
| Infrastructure | GKE Autopilot, Terraform, Docker |
| CI/CD | GitHub Actions + Cloud Deploy |

## Getting Started

### Prerequisites
- Python 3.11+
- Docker & Docker Compose
- Terraform 1.5+
- Google Cloud SDK (`gcloud`)

### Local Development
```bash
# Clone and setup
cp config/.env.example config/.env.local
pip install -r requirements.txt

# Run database migrations
python scripts/db/migrate.py

# Start development server
uvicorn src.api.main:app --reload --port 8000
```

## Environments

| Environment | Purpose | GCP Project |
|-------------|---------|-------------|
| Development | Local + dev cluster | `naca-chatbot-dev` |
| Staging | Pre-production testing | `naca-chatbot-staging` |
| Production | Live national deployment | `naca-chatbot-prod` |

## Documentation

- [Architecture Design Document](docs/architecture/ARCHITECTURE.md)
- [API Contracts (OpenAPI)](docs/api_contracts/)
- [Database Schema](docs/schemas/)
- [Operational Runbooks](docs/runbooks/)

## License

Proprietary — National Agency for the Control of AIDS (NACA), Federal Republic of Nigeria
