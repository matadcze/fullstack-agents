# Backend (FastAPI) Template

Scaffolding for a production-ready FastAPI service: authentication and audit routes, async SQLAlchemy + Alembic migrations, Celery worker, Redis-powered rate limiting, structured logging, and Prometheus metrics.

## Getting Started

1) Copy environment:
```
cp .env.example .env
```
Fill in `DATABASE_URL`, `JWT_SECRET_KEY`, and any other required values.

2) Install dependencies:
```
uv sync
```

3) Run migrations (uses `DATABASE_URL`):
```
uv run alembic upgrade head
```

4) Start the API:
```
uv run uvicorn src.api.app:app --reload
```

Optional:
- Celery worker: `uv run celery -A src.worker.celery_app worker --loglevel=info`
- Celery beat: `uv run celery -A src.worker.celery_app beat --loglevel=info`

## Developer Tooling
- Linting/formatting: `make backend-lint` (ruff + black) and `make backend-format` (isort + black + ruff --fix) from the repo root.
- Type checks: `make backend-typecheck` (mypy) for quick regressions in types.
- Git hooks: `make pre-commit-install` to install hooks; run on demand with `make pre-commit`.
- Seed data: `make seed` creates fixture users (admin@example.com / ChangeMe123! and demo@example.com / DemoPass123!) plus sample audit events. Safe to rerun.

## Project Layout

- `src/api`: FastAPI app factory, routers, middleware, schemas
- `src/domain`: Entities, exceptions, repository interfaces, services
- `src/infrastructure`: Database models/sessions, auth utilities, metrics provider
- `src/worker`: Celery configuration and sample task
- `alembic`: Migrations; `alembic.ini` + `alembic/env.py`

## Endpoints

- `GET /api/v1/health` – basic liveness
- `GET /api/v1/readiness` – checks DB/Redis/storage connectivity
- `GET /metrics` – Prometheus exposition
- `POST /api/v1/auth/register|login|refresh`
- `PUT /api/v1/auth/change-password|profile`
- `GET/DELETE /api/v1/auth/me`
- `GET /api/v1/audit` – list audit events
- `POST /api/v1/agents/run` – sample agent endpoint (stubbed provider)

### Refresh-token rotation

Refreshing requires a valid refresh JWT, an unrevoked and unexpired stored token
belonging to the same user, and an active user account. Refresh JWTs include a unique
`jti` so tokens issued within the same second remain distinct.

Rotation conditionally consumes the stored token and inserts its replacement in
the same database transaction. Only one concurrent refresh can succeed; reusing a
consumed token returns HTTP 401. The request database dependency commits on success
and rolls back on failure, including when replacement storage fails. Other callers
of the repository must also roll back their transaction on errors.

### Cross-origin authentication challenges

CORS exposes `WWW-Authenticate` to allowed origins, including the local web app at
`http://localhost:3000`. The browser client uses the Bearer challenge to distinguish
expired access tokens from incorrect-current-password errors on password changes:
only token failures trigger refresh and a single retry. Preserve this exposure
when changing CORS settings; the allowed-origin list remains unchanged.

The browser regression uses the real API with isolated in-memory SQLite/Redis
and a separate HTTP origin, without requiring Postgres, Redis, or Next.js:

```bash
# From the repo root, after uv sync and pnpm install:
cd apps/web
PLAYWRIGHT_BASE_URL=http://unused pnpm exec playwright test cors-auth.spec.ts --workers=1
```

It defaults to the workspace `.venv`; set `PLAYWRIGHT_API_PYTHON` to use another
Python interpreter with the API's development dependencies installed.

Use `{{PROJECT_NAME}}` placeholders throughout when creating a new project; see the root README for the templating checklist.
