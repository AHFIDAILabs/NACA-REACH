# =============================================================================
# NACA AI HIV Chatbot — Makefile
# =============================================================================

.PHONY: help install dev setup db-up db-down db-migrate db-seed run test lint fmt docker-build docker-up docker-down clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Setup ────────────────────────────────────────────────────────────────────

install: ## Install production dependencies
	pip install -r requirements.txt

dev: ## Install all dependencies (production + dev/test)
	pip install -r requirements.txt -r requirements-dev.txt

setup: dev db-up db-migrate db-seed ## Full setup: install deps, start DB, migrate, seed
	@echo "✅ Setup complete. Run 'make run' to start the server."

# ── Database ─────────────────────────────────────────────────────────────────

db-up: ## Start PostgreSQL, Redis, Qdrant via Docker Compose
	docker compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 3
	@docker compose ps

db-down: ## Stop all Docker Compose services
	docker compose down

db-migrate: ## Run database schema migration
	@echo "Applying database schema..."
	PGPASSWORD=naca_dev psql -h localhost -U naca -d naca_chatbot -f scripts/db/001_initial_schema.sql 2>/dev/null || \
		docker compose exec -T postgres psql -U naca -d naca_chatbot -f /docker-entrypoint-initdb.d/001_initial_schema.sql
	@echo "✅ Schema applied."

db-seed: ## Load sample facility and knowledge base data
	@echo "Loading seed data..."
	PGPASSWORD=naca_dev psql -h localhost -U naca -d naca_chatbot -f scripts/seed_data/001_sample_facilities.sql 2>/dev/null || \
		docker compose exec -T postgres psql -U naca -d naca_chatbot < scripts/seed_data/001_sample_facilities.sql
	@echo "✅ Seed data loaded."

db-reset: db-down db-up ## Reset database (destroy and recreate)
	@sleep 3
	@echo "✅ Database reset."

# ── Run ──────────────────────────────────────────────────────────────────────

run: ## Start the development server
	PYTHONPATH=. uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000

run-prod: ## Start the production server (gunicorn)
	gunicorn src.api.main:app \
		--worker-class uvicorn.workers.UvicornWorker \
		--workers 4 \
		--bind 0.0.0.0:8000 \
		--timeout 120

# ── Test ─────────────────────────────────────────────────────────────────────

test: ## Run all unit tests
	PYTHONPATH=. pytest tests/unit/ -v --tb=short

test-cov: ## Run tests with coverage report
	PYTHONPATH=. pytest tests/unit/ -v --cov=src --cov-report=term-missing --cov-report=html

test-watch: ## Run tests in watch mode (requires pytest-watch)
	PYTHONPATH=. ptw tests/unit/ -- -v --tb=short

# ── Code Quality ─────────────────────────────────────────────────────────────

lint: ## Run linter
	ruff check src/ tests/

fmt: ## Format code
	ruff format src/ tests/

typecheck: ## Run type checker
	mypy src/ --ignore-missing-imports

security: ## Run security scan
	bandit -r src/ -ll --skip B101
	safety check || true

check: lint typecheck test ## Run all checks (lint + typecheck + test)

# ── Docker ───────────────────────────────────────────────────────────────────

docker-build: ## Build the application Docker image
	docker build -f infrastructure/docker/Dockerfile -t naca-chatbot:latest .

docker-up: ## Start full stack (app + dependencies)
	docker compose -f docker-compose.yml -f docker-compose.app.yml up -d

docker-down: ## Stop full stack
	docker compose -f docker-compose.yml -f docker-compose.app.yml down

# ── Utilities ────────────────────────────────────────────────────────────────

clean: ## Remove build artifacts and caches
	find . -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	find . -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
	find . -name '*.pyc' -delete 2>/dev/null || true
	rm -rf .mypy_cache htmlcov .coverage build dist *.egg-info
