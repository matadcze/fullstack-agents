.PHONY: help install api-install web-install api-dev web-dev dev api-test web-test test api-lint web-lint lint api-format web-format format api-typecheck pre-commit-install pre-commit seed clean docker-build docker-up docker-down docker-dev-prepare docker-dev-up

help:
	@echo "{{PROJECT_NAME}} - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install              Install all dependencies"
	@echo "  make api-install          Install API dependencies"
	@echo "  make web-install          Install web dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make dev                  Run API and web in parallel"
	@echo "  make api-dev              Run API server (port 8000)"
	@echo "  make web-dev              Run web dev server (port 3000)"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test                 Run API tests"
	@echo "  make api-test             Run API tests"
	@echo "  make web-test             Run web Playwright tests"
	@echo "  make lint                 Run linters"
	@echo "  make api-lint             Lint API code"
	@echo "  make web-lint             Lint web code"
	@echo "  make api-format           Format API code"
	@echo "  make web-format           Format web code"
	@echo "  make format               Format API + web"
	@echo "  make api-typecheck        Run mypy on the API"
	@echo "  make pre-commit-install   Install git hooks (pre-commit)"
	@echo "  make pre-commit           Run all pre-commit hooks"
	@echo "  make seed                 Seed local dev data"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-dev-prepare   Install api/web deps into dev volumes for hot reload"
	@echo "  make docker-dev-up        Run api+web+nginx with dev override (hot reload)"
	@echo "  make docker-build         Build Docker images"
	@echo "  make docker-up            Start Docker containers"
	@echo "  make docker-down          Stop Docker containers"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean                Remove all generated files"


install: api-install web-install
	@echo "All dependencies installed"

api-install:
	@echo "Installing API dependencies..."
	cd apps/api && uv sync

web-install:
	@echo "Installing web dependencies..."
	cd apps/web && npm install

dev:
	@echo "Starting development servers..."
	@echo "   API:      http://localhost:8000"
	@echo "   Web:      http://localhost:3000"
	@echo "   API Docs: http://localhost:8000/api/docs"
	$(MAKE) -j2 api-dev web-dev

api-dev:
	cd apps/api && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

web-dev:
	cd apps/web && npm run dev


test: api-test
	@echo "All tests passed"

api-test:
	@echo "Running API tests..."
	cd apps/api && uv run pytest -v

web-test:
	@echo "Running web tests (Playwright)..."
	cd apps/web && npm run test:e2e

lint: api-lint web-lint
	@echo "All linters passed"

api-lint:
	@echo "Linting API code..."
	cd apps/api && uv run ruff check . && uv run black --check .

web-lint:
	@echo "Linting web code..."
	cd apps/web && npm run lint

api-format:
	@echo "Formatting API code..."
	cd apps/api && uv run isort . && uv run black . && uv run ruff check --fix .

web-format:
	@echo "Formatting web code..."
	cd apps/web && npm run format

format: api-format web-format
	@echo "Formatting complete"

api-typecheck:
	@echo "Type checking API code..."
	cd apps/api && uv run mypy --config-file pyproject.toml src

pre-commit-install:
	@echo "Installing pre-commit git hooks..."
	cd apps/api && uv run pre-commit install

pre-commit:
	@echo "Running pre-commit hooks..."
	cd apps/api && uv run pre-commit run --all-files

seed:
	@echo "Seeding local development data..."
	cd apps/api && uv run python -m scripts.seed_data


docker-build:
	@echo "Building Docker images..."
	docker compose build

docker-up:
	@echo "Starting Docker containers..."
	docker compose up -d
	@echo "Services running:"
	@echo "   Gateway: http://localhost"
	@echo "   API:     http://localhost:8000"
	@echo "   Web:     http://localhost:3000"

docker-down:
	@echo "Stopping Docker containers..."
	docker compose down

docker-dev-prepare:
	@echo "Installing API dependencies into dev volume..."
	docker compose -f docker-compose.yml -f docker-compose.override.yml run --rm api uv sync --frozen --group dev
	@echo "Installing web dependencies into dev volume..."
	docker compose -f docker-compose.yml -f docker-compose.override.yml run --rm web npm ci --include=dev

docker-dev-up:
	@echo "Starting dev stack with hot reload (api+web+nginx)..."
	docker compose -f docker-compose.yml -f docker-compose.override.yml up api web nginx


clean:
	@echo "Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name .DS_Store -delete 2>/dev/null || true
	cd apps/api && rm -rf .venv 2>/dev/null || true
	cd apps/web && rm -rf node_modules 2>/dev/null || true
	@echo "Cleanup complete"

.DEFAULT_GOAL := help
