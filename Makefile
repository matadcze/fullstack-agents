.PHONY: help install backend-install frontend-install backend-dev frontend-dev dev backend-test frontend-test test backend-lint frontend-lint lint clean docker-build docker-up docker-down

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
	@echo "  make test                 Run all tests"
	@echo "  make backend-test         Run backend tests"
	@echo "  make lint                 Run linters"
	@echo "  make backend-lint         Lint backend code"
	@echo "  make backend-format       Format backend code"
	@echo ""
	@echo "Docker:"
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

lint: backend-lint
	@echo "All linters passed"

backend-lint:
	@echo "Linting backend code..."
	cd backend && uv run ruff check . && uv run black --check .

backend-format:
	@echo "Formatting backend code..."
	cd backend && uv run black . && uv run ruff check --fix .


docker-build:
	@echo "Building Docker images..."
	docker compose build

docker-up:
	@echo "Starting Docker containers..."
	docker compose up -d
	@echo "Services running:"
	@echo "   Backend:  http://localhost:8000"
	@echo "   Frontend: http://localhost:3000"

docker-down:
	@echo "Stopping Docker containers..."
	docker compose down


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
