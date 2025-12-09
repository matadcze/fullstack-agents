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
cp .env.example .env
cp backend/.env.example backend/.env
```
   - Set `DATABASE_URL`, `JWT_SECRET_KEY` (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`), and adjust any hostnames/ports.
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
Services: backend `:8000`, frontend `:3000`, Prometheus `:9091`, Grafana `:3001` (admin/admin).

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
- Canonical example: `.env.example` (root) and `backend/.env.example`
- Key values: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `NEXT_PUBLIC_API_URL`, `APP_NAME`, `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`
- Docker Compose reads `backend/.env` for backend + frontend containers.

## Testing
- Backend: `make backend-test` (pytest sample health test)
- Frontend: `npm run test:e2e` (Playwright sample, adjust selectors as you extend UI)

## Next Steps
- Add your domains: extend `backend/src/domain` and `backend/src/api/v1`
- Expand frontend pages/components for your use case
- Wire CI/CD (lint, test, build images) for your target platform
