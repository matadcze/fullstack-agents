# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A production-ready polyglot monorepo template: FastAPI (Python) + Next.js (TypeScript) + Rust, with JWT auth, audit logging, Celery workers, Prometheus/Grafana observability, and Docker Compose. Rust can be used as standalone services or compiled into Python extensions (PyO3) and WASM modules (wasm-bindgen) for direct import into the other apps.

The codebase contains template placeholders (`{{PROJECT_NAME}}`, `{{PROJECT_NAME_SLUG}}`) that should be replaced when creating a new project from it.

## Project Layout

```
apps/
  api/          # FastAPI service (Python/uv)
  web/          # Next.js app (TypeScript/pnpm)
  rust-svc/     # Rust binary service
packages/
  py-core/      # PyO3 crate → .so imported by apps/api
  wasm-core/    # wasm-bindgen crate → WASM imported by apps/web
  ts-shared/    # Shared TypeScript types (pnpm workspace)
nginx/          # Reverse proxy config
prometheus/     # Scrape config + alert rules
grafana/        # Provisioning + dashboards
```

**Workspace roots:**
- `Cargo.toml` — Cargo workspace (`apps/rust-svc`, `packages/py-core`, `packages/wasm-core`)
- `pyproject.toml` — uv workspace (`apps/api`)
- `pnpm-workspace.yaml` — pnpm workspace (`apps/web`, `packages/ts-shared`)
- `.moon/` — Moon task runner (cross-language build graph, caching, `dependsOn`)

## Getting the App Running

Follow these steps in order on a fresh clone. All commands run from the repo root.

### 1. Check prerequisites

```bash
cargo --version      # Rust stable
uv --version         # Python package manager
node --version       # ≥ 22
pnpm --version       # ≥ 9
moon --version       # moonrepo task runner
docker --version     # for Postgres/Redis (or full-stack path)
```

Install anything missing:
```bash
curl https://sh.rustup.rs -sSf | sh                              # Rust
curl -LsSf https://astral.sh/uv/install.sh | sh                 # uv
npm install -g pnpm                                              # pnpm
curl -fsSL https://moonrepo.dev/install/moon.sh | bash          # Moon
```

### 2. Configure env files

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env
```

Required in `apps/api/.env`:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/<dbname>
JWT_SECRET_KEY=<run: python3 -c "import secrets; print(secrets.token_urlsafe(32))">
REDIS_URL=redis://localhost:6379/0
```

Required in `apps/web/.env` (or `.env.local`):
```
NEXT_PUBLIC_API_URL=http://localhost:8000   # local dev
# NEXT_PUBLIC_API_URL=https://localhost     # Docker/nginx
```

### 3. Install dependencies

```bash
make install      # uv sync + pnpm install + cargo fetch
```

### 4. Choose a run path

**Path A — Local dev (Postgres + Redis via Docker, servers native):**
```bash
docker compose up -d postgres redis          # infrastructure only
cd apps/api && uv run alembic upgrade head   # run migrations
make seed                                    # optional: fixture data
make dev                                     # API :8000 + web :3000
```

**Path B — Full Docker stack:**
```bash
docker compose up -d --build   # builds all images, starts everything
make seed                      # optional: fixture data (runs inside api container)
```
Services: web https://localhost · API http://localhost:8000 · Grafana http://localhost:3001

**Path C — Docker dev with hot reload:**
```bash
make docker-dev-prepare   # installs deps into named volumes (first time only)
make docker-dev-up        # api + web + nginx with source mounted
```

### 5. Verify

```bash
curl http://localhost:8000/api/v1/health    # {"status":"ok"}
open http://localhost:3000                  # web app
open http://localhost:8000/api/docs         # Swagger UI
moon run :build                             # build graph passes
```

---

## Common Commands

All commands run from the repo root via `make` or `moon`.

### Setup
```bash
make install            # uv sync + pnpm install + cargo fetch
make api-install        # uv sync only
make web-install        # pnpm install only
make rust-install       # cargo fetch only

# Moon CLI (install once): curl -fsSL https://moonrepo.dev/install/moon.sh | bash
# wasm-pack (for WASM builds): cargo install wasm-pack
# maturin (for PyO3 builds): pip install maturin
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

### Rust
```bash
make rust-build         # cargo build --workspace (all Rust members)

# PyO3 extension (dev install into current venv)
moon run py-core:develop    # maturin develop

# WASM module
moon run wasm-core:build    # wasm-pack build → packages/wasm-core/pkg/
```

### Moon (cross-language, cached)
```bash
moon run :build         # build all projects in dependency order
moon run :test          # test all projects
moon run api:dev        # run a single project's task
moon run web:build      # build web (waits for wasm-core + ts-shared first)
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
- Local Next.js dev (`pnpm dev`): set to `http://localhost:8000` in `apps/web/.env.local`
- Docker/nginx: set to `https://localhost` (nginx terminates TLS)

## Rust Packages

**`packages/py-core`** — PyO3 extension module compiled to a native `.so` and imported by `apps/api`:
- Build: `maturin develop` (dev) or `maturin build --release` (wheel)
- Moon handles build ordering: `api:build` depends on `py-core:build`

**`packages/wasm-core`** — wasm-bindgen crate compiled to WebAssembly for use in `apps/web`:
- Build: `wasm-pack build --target web --out-dir pkg`
- Output lands in `packages/wasm-core/pkg/`; reference as `file:../../packages/wasm-core/pkg` in web's `package.json`
- Moon handles build ordering: `web:build` depends on `wasm-core:build`

**`apps/rust-svc`** — standalone Rust binary service, deployed as its own container:
- Build: `cargo build --release -p rust-svc`

## Moon Task Runner

`.moon/workspace.yml` auto-discovers all projects under `apps/` and `packages/`. Each project has a `moon.yml` defining tasks and their `dependsOn` graph.

Cross-language dependency example:
```
web:build → wasm-core:build (Rust compiles first)
web:build → ts-shared:build
api:build → py-core:build (Rust compiles first)
```

Moon caches task outputs by content hash — unchanged Rust crates don't recompile on every `moon run :build`.

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
