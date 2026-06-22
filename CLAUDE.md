# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A production-ready fullstack template: FastAPI (Python) + Next.js (TypeScript), with JWT auth, audit logging, Celery workers, Prometheus/Grafana observability, and Docker Compose. The codebase contains template placeholders (`{{PROJECT_NAME}}`, `{{PROJECT_NAME_SLUG}}`) that should be replaced when creating a new project from it.

## Project Layout

```
apps/
  api/      # FastAPI service (Python/uv)
  web/      # Next.js app (TypeScript/npm)
nginx/      # Reverse proxy config
prometheus/ # Scrape config + alert rules
grafana/    # Provisioning + dashboards
```

## Common Commands

All commands run from the repo root via `make`. The `apps/api/` and `apps/web/` directories use `uv` and `npm` respectively.

### Setup
```bash
make api-install        # uv sync
make web-install        # npm install
# Or both at once:
make install
```

### Local development (no Docker)
```bash
# First-time: copy and fill in env files
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env

# Run migrations
cd apps/api && uv run alembic upgrade head

# Start both servers (ports 8000 + 3000)
make dev
```

### Testing
```bash
make api-test                         # pytest
make web-test                         # Playwright e2e

# Single test file
cd apps/api && uv run pytest tests/test_api/test_health.py -v

# Single test by name
cd apps/api && uv run pytest -k "test_health" -v
```

### Lint & format
```bash
make api-lint           # ruff check + black --check
make web-lint           # eslint
make api-format         # isort + black + ruff --fix
make web-format         # prettier
make api-typecheck      # mypy
make lint               # both
make format             # both
```

### Docker
```bash
# Full stack (prod-like)
docker compose up -d --build

# Dev mode with hot reload
make docker-dev-prepare   # installs deps into named volumes
make docker-dev-up        # starts api + web + nginx with volume mounts

# Seed fixture data (admin@example.com / ChangeMe123!)
make seed
```

### Database migrations
```bash
# From apps/api/
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"
uv run alembic downgrade -1
```

## API Architecture

The API follows clean architecture with strict layer separation:

```
src/
  domain/         # Pure Python: entities, repository ABCs, services, value objects
  infrastructure/ # Implementations: SQLAlchemy repos, JWT, Celery, metrics
  api/            # FastAPI: app factory, routers, middleware, Pydantic schemas
  core/           # Config (pydantic-settings), logging, metrics
  worker/         # Celery app + tasks
```

**Key patterns:**
- `src/domain/repositories.py` defines ABCs (`UserRepository`, `AuditEventRepository`, `RefreshTokenRepository`). Implementations live in `src/infrastructure/repositories/`.
- `src/domain/entities.py` holds Pydantic models (`User`, `AuditEvent`, `RefreshToken`) — separate from SQLAlchemy models in `src/infrastructure/database/models.py`.
- `src/api/app.py` contains `create_app()` factory; `main.py` is the uvicorn entrypoint (`uvicorn main:app`).
- FastAPI dependency injection for auth: `get_current_user` / `get_current_user_id` in `src/infrastructure/auth/dependencies.py`.
- All errors are wrapped in `ErrorResponse(error: ErrorDetail)` with a correlation ID header (`X-Correlation-ID`).

**LLM/Agent scaffold:**
- `src/infrastructure/agents/providers.py` exposes `get_llm_provider()` which returns `StubLLMProvider` by default.
- To wire a real LLM, implement the `LLMProvider` ABC from `src/domain/services/agent_service.py` and branch on `settings.llm_provider` in `get_llm_provider()`.

**Config** (`src/core/config.py`): loaded from `.env` via `pydantic-settings`. Required env vars: `DATABASE_URL`, `JWT_SECRET_KEY`. Optional: `REDIS_URL`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`.

Generate a JWT secret: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## Web Architecture

Next.js App Router (`src/app/`). Auth state is managed by `AuthContext` (`src/contexts/AuthContext.tsx`), which wraps the app in `src/app/layout.tsx`.

**Key files:**
- `src/lib/api/client.ts` — singleton `apiClient` with namespaced methods (`apiClient.auth.*`, `apiClient.audit.*`, `apiClient.agents.*`). Stores tokens in `localStorage`.
- `src/lib/types/api.ts` — TypeScript types mirroring API response schemas.
- `src/components/ProtectedRoute.tsx` — wraps pages that require authentication.
- `src/hooks/useApi.ts` — custom hooks for data fetching.

**`NEXT_PUBLIC_API_URL`** controls the API base URL:
- Local Next.js dev (`npm run dev`): set to `http://localhost:8000` in `apps/web/.env.local`
- Docker/nginx: set to `https://localhost` (nginx terminates TLS)

## Services & Ports

| Service    | Port  | Notes                          |
|------------|-------|--------------------------------|
| API        | 8000  | FastAPI, docs at `/api/docs`   |
| Web        | 3000  | Next.js                        |
| nginx      | 80/443| Reverse proxy (Docker only)    |
| Postgres   | 5432  |                                |
| Redis      | 6379  |                                |
| Prometheus | 9091  |                                |
| Grafana    | 3001  | admin/admin                    |
| pgAdmin    | 5050  |                                |
