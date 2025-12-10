.PHONY: help install backend-install frontend-install backend-dev frontend-dev dev backend-test frontend-test test backend-lint frontend-lint lint backend-format frontend-format format backend-typecheck pre-commit-install pre-commit seed clean docker-build docker-up docker-down docker-dev-prepare docker-dev-up

help:
	@echo "{{PROJECT_NAME}} - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install              Install all dependencies"
	@echo "  make backend-install      Install backend dependencies"
	@echo "  make frontend-install     Install frontend dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make dev                  Run backend and frontend in parallel"
	@echo "  make backend-dev          Run backend API server (port 8000)"
	@echo "  make frontend-dev         Run frontend dev server (port 3000)"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test                 Run backend tests"
	@echo "  make backend-test         Run backend tests"
	@echo "  make frontend-test        Run frontend Playwright tests"
	@echo "  make lint                 Run linters"
	@echo "  make backend-lint         Lint backend code"
	@echo "  make frontend-lint        Lint frontend code"
	@echo "  make backend-format       Format backend code"
	@echo "  make frontend-format      Format frontend code"
	@echo "  make format               Format backend + frontend"
	@echo "  make backend-typecheck    Run mypy on the backend"
	@echo "  make pre-commit-install   Install git hooks (pre-commit)"
	@echo "  make pre-commit           Run all pre-commit hooks"
	@echo "  make seed                 Seed local dev data"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-dev-prepare   Install backend/frontend deps into dev volumes for hot reload"
	@echo "  make docker-dev-up        Run backend+frontend+nginx with dev override (hot reload)"
	@echo "  make docker-build         Build Docker images"
	@echo "  make docker-up            Start Docker containers"
	@echo "  make docker-down          Stop Docker containers"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean                Remove all generated files"


install: backend-install frontend-install
	@echo "All dependencies installed"

backend-install:
	@echo "Installing backend dependencies..."
	cd backend && uv sync

frontend-install:
	@echo "Installing frontend dependencies..."
	cd frontend && npm install

dev:
	@echo "Starting development servers..."
	@echo "   Backend:  http://localhost:8000"
	@echo "   Frontend: http://localhost:3000"
	@echo "   API Docs: http://localhost:8000/api/docs"
	$(MAKE) -j2 backend-dev frontend-dev

backend-dev:
	cd backend && uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000

frontend-dev:
	cd frontend && npm run dev


test: backend-test
	@echo "All tests passed"

backend-test:
	@echo "Running backend tests..."
	cd backend && uv run pytest -v

frontend-test:
	@echo "Running frontend tests (Playwright)..."
	cd frontend && npm run test:e2e

lint: backend-lint frontend-lint
	@echo "All linters passed"

backend-lint:
	@echo "Linting backend code..."
	cd backend && uv run ruff check . && uv run black --check .

frontend-lint:
	@echo "Linting frontend code..."
	cd frontend && npm run lint

backend-format:
	@echo "Formatting backend code..."
	cd backend && uv run isort . && uv run black . && uv run ruff check --fix .

frontend-format:
	@echo "Formatting frontend code..."
	cd frontend && npm run format

format: backend-format frontend-format
	@echo "Formatting complete"

backend-typecheck:
	@echo "Type checking backend code..."
	cd backend && uv run mypy --config-file pyproject.toml src

pre-commit-install:
	@echo "Installing pre-commit git hooks..."
	cd backend && uv run pre-commit install

pre-commit:
	@echo "Running pre-commit hooks..."
	cd backend && uv run pre-commit run --all-files

seed:
	@echo "Seeding local development data..."
	cd backend && uv run python -m scripts.seed_data


docker-build:
	@echo "Building Docker images..."
	docker compose build

docker-up:
	@echo "Starting Docker containers..."
	docker compose up -d
	@echo "Services running:"
	@echo "   Gateway: http://localhost"
	@echo "   Backend:  http://localhost:8000"
	@echo "   Frontend: http://localhost:3000"

docker-down:
	@echo "Stopping Docker containers..."
	docker compose down

docker-dev-prepare:
	@echo "Installing backend dependencies into dev volume..."
	docker compose -f docker-compose.yml -f docker-compose.override.yml run --rm backend uv sync --frozen --group dev
	@echo "Installing frontend dependencies into dev volume..."
	docker compose -f docker-compose.yml -f docker-compose.override.yml run --rm frontend npm ci --include=dev

docker-dev-up:
	@echo "Starting dev stack with hot reload (backend+frontend+nginx)..."
	docker compose -f docker-compose.yml -f docker-compose.override.yml up backend frontend nginx


clean:
	@echo "Cleaning up..."
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name .DS_Store -delete 2>/dev/null || true
	cd backend && rm -rf .venv 2>/dev/null || true
	cd frontend && rm -rf node_modules 2>/dev/null || true
	@echo "Cleanup complete"

.DEFAULT_GOAL := help
