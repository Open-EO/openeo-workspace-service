# ---------------------------------------------------------------------------
# openeo-workspace-service – developer convenience targets
# ---------------------------------------------------------------------------

.DEFAULT_GOAL := help
PYTHON        ?= python3
SRC           := src/openeo_workspace_service
TESTS         := tests
DC            := docker compose -f docker/docker-compose.yml

# ---- Colours ---------------------------------------------------------------
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RESET  := \033[0m

.PHONY: help install install-dev lint format typecheck test test-unit test-integration \
        cov up down logs shell seed-providers get-token migrate-status clean

help:   ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-22s$(RESET) %s\n", $$1, $$2}'

# ---- Installation ----------------------------------------------------------

install:        ## Install runtime dependencies
	pip install -e .

install-dev:    ## Install all dependencies including dev/test extras
	pip install -e ".[dev]"
	pre-commit install

# ---- Code quality ----------------------------------------------------------

lint:           ## Run ruff linter
	ruff check $(SRC) $(TESTS)

format:         ## Run ruff formatter
	ruff format $(SRC) $(TESTS)

format-check:   ## Check formatting without modifying files
	ruff format --check $(SRC) $(TESTS)

typecheck:      ## Run mypy type checker
	mypy $(SRC)

check: lint format-check typecheck  ## Run all code-quality checks

# ---- Testing ---------------------------------------------------------------

test:           ## Run the full test suite
	pytest $(TESTS) -v

test-unit:      ## Run unit tests only
	pytest $(TESTS)/unit -v

test-integration:  ## Run integration tests only
	pytest $(TESTS)/integration -v

cov:            ## Run tests with HTML coverage report
	pytest $(TESTS) --cov=$(SRC) --cov-report=html --cov-report=term-missing
	@echo "$(YELLOW)Coverage report: htmlcov/index.html$(RESET)"

cov-xml:        ## Run tests with XML coverage (for CI)
	pytest $(TESTS) --cov=$(SRC) --cov-report=xml

# ---- Local dev stack -------------------------------------------------------

up:             ## Start the full dev stack (ES + Keycloak + service)
	$(DC) up -d
	@echo "$(GREEN)Services started:$(RESET)"
	@echo "  API:      http://localhost:8000"
	@echo "  Docs:     http://localhost:8000/docs"
	@echo "  Keycloak: http://localhost:8080  (admin/admin)"
	@echo "  ES:       http://localhost:9200"

up-debug:       ## Start the full dev stack including Kibana
	$(DC) --profile debug up -d

down:           ## Stop the dev stack
	$(DC) down

logs:           ## Tail logs from all services
	$(DC) logs -f

logs-svc:       ## Tail logs from the workspace service only
	$(DC) logs -f workspace-svc

shell:          ## Open a shell in the running workspace-svc container
	$(DC) exec workspace-svc /bin/sh

# ---- Data management -------------------------------------------------------

seed-providers: ## Seed default workspace providers into Elasticsearch
	$(PYTHON) scripts/seed_providers.py

seed-reset:     ## Reset and re-seed workspace providers
	$(PYTHON) scripts/seed_providers.py --reset

get-token:      ## Fetch a Keycloak Bearer token for alice (local dev)
	@bash scripts/get_token.sh alice alice123

get-token-admin: ## Fetch a Keycloak Bearer token for admin-user
	@bash scripts/get_token.sh admin-user admin123

migrate-status: ## Show Elasticsearch index health and document counts
	$(PYTHON) -m openeo_workspace_service.db.migrations status

# ---- Docker image ----------------------------------------------------------

build:          ## Build the Docker image
	docker build -f docker/Dockerfile -t openeo-workspace-service:dev .

# ---- Cleanup ---------------------------------------------------------------

clean:          ## Remove Python build artefacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage htmlcov coverage.xml .mypy_cache .ruff_cache dist build *.egg-info
