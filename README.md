# {{PROJECT_NAME}} Full-Stack Template

Reusable FastAPI + React (Next.js) starter with JWT auth, audit logging, async SQLAlchemy, Celery workers, Docker Compose, Prometheus, and Grafana dashboards.

## What's Included
- **Backend (FastAPI)**: Auth & audit routes, async SQLAlchemy + Alembic, Redis-backed rate limiting, Prometheus metrics, structured logging, Celery worker/beat scaffolding.
- **Frontend (Next.js + TypeScript)**: Auth flows (login/register/profile), protected dashboard shell, typed API client, Tailwind styles.
- **Agent scaffold**: Stub LLM provider with `/api/v1/agents/run` endpoint and frontend demo page to submit prompts.
- **Ops**: Docker Compose for Postgres, Redis, backend, frontend, Prometheus, Grafana; health/readiness endpoints; Makefile helpers.

## Using This Template
1) Replace placeholders:
   - `{{PROJECT_NAME}}` → human-readable name
   - `{{PROJECT_NAME_SLUG}}` / `{{PROJECT_NAME_LOWER}}` → lowercase/slug used in container names and defaults

2) Copy env files and fill in secrets:
```
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```
   - Set `DATABASE_URL`, `JWT_SECRET_KEY` (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`), and adjust any hostnames/ports.
   - When using Docker/nginx, set `NEXT_PUBLIC_API_URL` to `https://localhost` in `frontend/.env` (nginx terminates TLS with the bundled self-signed cert). For local Next.js dev (`npm run dev`) that talks directly to the backend, override to `http://localhost:8000` in `frontend/.env.local`.
   - For local Next.js runs, you can also place `NEXT_PUBLIC_*` values in `frontend/.env.local`.

3) Local dev (no Docker):
```
make backend-install
make frontend-install
cd backend && uv run alembic upgrade head
make dev   # runs uvicorn + next dev
```

4) Full stack with Docker:
```
docker compose up -d --build
```
Services: nginx entrypoint `:80` (proxies frontend + backend), backend `:8000`, frontend `:3000`, Prometheus `:9091`, Grafana `:3001` (admin/admin).

## Developer Tooling
- Git hooks: `make pre-commit-install` to add hooks (ruff/black/isort/mypy + frontend lint/format). Run on demand with `make pre-commit`.
- Lint/format: `make lint` (backend + frontend) and `make format` to apply fixes. Backend type checks via `make backend-typecheck`.
- Sample data: `make seed` loads fixture users (e.g., admin@example.com / ChangeMe123!) and basic audit events for local testing.
- Frontend formatting uses Prettier; linting runs ESLint flat config in `frontend/eslint.config.mjs`.

## Project Structure
```
.
├── backend/          # FastAPI service, Alembic migrations, Celery worker
├── frontend/         # Next.js app with auth flows
├── prometheus/       # Prometheus scrape config
├── grafana/          # Provisioning + dashboards
├── docker-compose.yml
└── Makefile
```

## Environment Variables
- Canonical examples: `backend/.env.example` and `frontend/.env.example`
- Key values: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `NEXT_PUBLIC_API_URL`, `APP_NAME`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`
- Docker Compose reads `backend/.env` for backend services and `frontend/.env` (with `NEXT_PUBLIC_API_URL=http://localhost`) for the nginx entrypoint.

## Scaling & Sessions
- **Backend workers**: The provided compose files run a single Uvicorn process. For horizontal scale, run multiple backend replicas behind nginx or a load balancer and set `UVICORN_WORKERS` (or switch to gunicorn+uvicorn workers) based on CPU cores. Keep migrations as a one-shot job to avoid race conditions when scaling.
- **Celery**: Scale `celery-worker` replicas independently for background throughput. `celery-beat` should stay singleton.
- **Sessions/state**: The app is stateless (JWT auth), so horizontal scaling is safe. Redis is used for rate limiting; if you add server-side sessions or websockets, plan for a shared store (Redis) and sticky sessions where needed.
- **Redis persistence**: Persistence is disabled by default (see compose files). Enable AOF/RDB only if you need durable state beyond caching/rate-limit counters. For production durability, use a managed Redis or mount a volume with the desired persistence mode.

## Testing
- Backend: `make backend-test` (pytest sample health test) and `make backend-typecheck` (mypy)
- Frontend: `make frontend-test` / `npm run test:e2e` (Playwright sample, adjust selectors as you extend UI)

## Next Steps
- Add your domains: extend `backend/src/domain` and `backend/src/api/v1`
- Expand frontend pages/components for your use case
- Wire CI/CD (lint, test, build images) for your target platform
