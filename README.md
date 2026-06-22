# {{PROJECT_NAME}} Full-Stack Template

Polyglot monorepo starter: FastAPI + Next.js + Rust, with JWT auth, audit logging, async SQLAlchemy, Celery workers, Docker Compose, Prometheus, and Grafana dashboards. Rust can run as a standalone service or be compiled into Python extensions (PyO3) and WASM modules (wasm-bindgen) for direct import.

## What's Included

- **Backend (FastAPI)**: Auth & audit routes, async SQLAlchemy + Alembic, Redis-backed rate limiting, Prometheus metrics, structured logging, Celery worker/beat scaffolding.
- **Frontend (Next.js + TypeScript)**: Auth flows (login/register/profile), protected dashboard shell, typed API client, Tailwind styles.
- **Rust**: Binary service scaffold (`apps/rust-svc`), PyO3 extension stub (`packages/py-core`), wasm-bindgen stub (`packages/wasm-core`), shared TS types (`packages/ts-shared`).
- **Agent scaffold**: Stub LLM provider with `/api/v1/agents/run` endpoint and frontend demo page to submit prompts.
- **Ops**: Docker Compose for Postgres, Redis, backend, frontend, Prometheus, Grafana; health/readiness endpoints; Makefile helpers; Moon task runner for cross-language cached builds.

## Project Structure

```
.
├── apps/
│   ├── api/          # FastAPI service (Python/uv)
│   ├── web/          # Next.js app (TypeScript/pnpm)
│   └── rust-svc/     # Rust binary service
├── packages/
│   ├── py-core/      # PyO3 crate → native .so for apps/api
│   ├── wasm-core/    # wasm-bindgen crate → WASM for apps/web
│   └── ts-shared/    # Shared TypeScript types
├── nginx/
├── prometheus/
├── grafana/
├── Cargo.toml        # Cargo workspace root
├── pyproject.toml    # uv workspace root
├── pnpm-workspace.yaml
├── docker-compose.yml
└── Makefile
```

## Getting Started

### Prerequisites

Install these once on your machine before anything else:

| Tool | Version | Install |
|------|---------|---------|
| Rust + cargo | stable | `curl https://sh.rustup.rs -sSf \| sh` |
| Python | ≥ 3.12 | [python.org](https://www.python.org/downloads/) or `brew install python` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | ≥ 22 | `brew install node` or [nodejs.org](https://nodejs.org) |
| pnpm | ≥ 9 | `npm install -g pnpm` or `corepack enable && corepack prepare pnpm@latest --activate` |
| Moon | latest | `curl -fsSL https://moonrepo.dev/install/moon.sh \| bash` |
| Docker Desktop | latest | [docker.com](https://www.docker.com/products/docker-desktop/) — needed for the full-stack path |

Optional (only needed when you start using the Rust extension stubs):

```bash
pip install maturin        # PyO3 → Python .so  (packages/py-core)
cargo install wasm-pack    # Rust → WASM         (packages/wasm-core)
```

Verify your environment:

```bash
cargo --version && python3 --version && uv --version
node --version && pnpm --version && moon --version
```

---

### Step 1 — Personalise the template

Replace placeholders across the repo:

```bash
# macOS / Linux
grep -rl '{{PROJECT_NAME}}' . | xargs sed -i '' 's/{{PROJECT_NAME}}/My App/g'
grep -rl '{{PROJECT_NAME_SLUG}}' . | xargs sed -i '' 's/{{PROJECT_NAME_SLUG}}/my-app/g'
grep -rl 'project-name-slug' . | xargs sed -i '' 's/project-name-slug/my-app/g'
```

### Step 2 — Configure environment files

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env
```

Minimum values to set in `apps/api/.env`:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/myapp
JWT_SECRET_KEY=<generate below>
REDIS_URL=redis://localhost:6379/0
```

Generate a JWT secret:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Set in `apps/web/.env` (or `.env.local` for local-only override):

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Step 3 — Install dependencies

```bash
make install
# Runs: uv sync (Python) + pnpm install (Node) + cargo fetch (Rust)
```

Verify the build graph works:

```bash
moon run :build
# rust-svc compiles; api wheel builds; py-core/wasm-core/web skip gracefully
# until maturin/wasm-pack/pnpm-install are complete
```

---

### Path A — Local dev (no Docker)

You still need Postgres and Redis running. The quickest way is Docker for just those two:

```bash
docker compose up -d postgres redis
```

Then run migrations and start the servers:

```bash
# 1. Apply database migrations
cd apps/api && uv run alembic upgrade head && cd ../..

# 2. (Optional) Load fixture data
make seed     # creates admin@example.com / ChangeMe123!

# 3. Start API (port 8000) + web (port 3000) in parallel
make dev
```

Open:
- Web app → http://localhost:3000
- API docs → http://localhost:8000/api/docs
- API health → http://localhost:8000/api/v1/health

### Path B — Full stack with Docker

Builds and starts every service (Postgres, Redis, API, Celery, Web, nginx, Prometheus, Grafana):

```bash
docker compose up -d --build
```

Wait ~30 s for migrations and health checks, then:

```bash
# (Optional) Seed fixture data inside the running container
make seed
```

Open:
- Web app → https://localhost (nginx, self-signed cert — accept the browser warning)
- API docs → http://localhost:8000/api/docs
- Prometheus → http://localhost:9091
- Grafana → http://localhost:3001 (admin / admin)
- pgAdmin → http://localhost:5050

### Path C — Docker dev mode (hot reload)

Runs API and web with source mounted for live reload, nginx for TLS:

```bash
# First time only — installs deps into named Docker volumes
make docker-dev-prepare

# Start api + web + nginx with hot reload
make docker-dev-up
```

## Cross-Language Builds (Moon)

Moon manages build ordering across languages automatically:

```bash
moon run :build     # builds everything in dependency order (cached)
moon run :test      # tests everything
moon run web:build  # builds web after wasm-core + ts-shared
moon run api:build  # builds api after py-core
```

Build graph:
```
api:build   ← py-core:build   (Rust → Python .so via maturin)
web:build   ← wasm-core:build (Rust → WASM via wasm-pack)
web:build   ← ts-shared:build (TypeScript types)
```

## Developer Tooling

- **Lint/format**: `make lint` and `make format` (runs ruff/black/isort for Python, eslint/prettier for TypeScript).
- **Type checks**: `make api-typecheck` (mypy).
- **Git hooks**: `make pre-commit-install`, then run on demand with `make pre-commit`.
- **Sample data**: `make seed` loads fixture users (`admin@example.com` / `ChangeMe123!`) and basic audit events.

## Environment Variables

Canonical examples: `apps/api/.env.example` and `apps/web/.env.example`

| Variable | Where | Notes |
|---|---|---|
| `DATABASE_URL` | api | Postgres connection string |
| `JWT_SECRET_KEY` | api | Generate with `secrets.token_urlsafe(32)` |
| `REDIS_URL` | api | For Celery + rate limiting |
| `NEXT_PUBLIC_API_URL` | web | `http://localhost:8000` (local), `https://localhost` (Docker) |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` | api | Optional — for the agent scaffold |

## Scaling & Sessions

- **Backend workers**: Single Uvicorn process by default. For horizontal scale, run multiple replicas behind nginx and set `UVICORN_WORKERS`. Keep Alembic migrations as a one-shot job.
- **Celery**: Scale `celery-worker` replicas independently. `celery-beat` must stay singleton.
- **Sessions/state**: Stateless JWT auth — safe to scale horizontally. Redis handles rate limiting.
- **Redis persistence**: Disabled by default. Enable AOF/RDB or use a managed Redis for durable state.

## Testing

```bash
make api-test       # pytest
make web-test       # Playwright e2e
moon run :test      # all projects (cached)
```

## Next Steps

- Add your domains: extend `apps/api/src/domain` and `apps/api/src/api/v1`
- Expand `apps/web/src` pages/components for your use case
- Add Rust logic to `packages/py-core` (PyO3) or `packages/wasm-core` (WASM) and import it
- Wire CI/CD: `moon run :build :test` as a single cached pipeline step
