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
uv run uvicorn src.api.app:app --reload --no-proxy-headers
```

Optional:
- Celery worker: `uv run celery -A src.worker.celery_app worker --loglevel=info`
- Celery beat: `uv run celery -A src.worker.celery_app beat --loglevel=info`

Local startup disables forwarded headers, so direct clients cannot override their IP.
The Docker image trusts no proxies by default. All Compose configurations explicitly trust
only nginx's fixed address on the gateway network; nginx overwrites client-supplied forwarding
headers. See the root README's trusted-proxy policy before deploying behind another proxy.

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

Use `{{PROJECT_NAME}}` placeholders throughout when creating a new project; see the root README for the templating checklist.
