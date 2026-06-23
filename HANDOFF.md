# SCAIVA — Handoff Document

> **Last updated:** 2026-06-23
> **Branch:** `main`
> **Version:** 1.33.0 (renamed from Dograh)
> **Status:** Clean working tree (10 modified + 10 untracked files, see below)

---

## 1. What Is This Project?

SCAIVA (S2 Connects AI Voice Agent) is an **open-source, self-hostable voice AI platform** for building and deploying conversational AI agents with telephony (Twilio, Telnyx, Plivo, Vonage, Acefone, Cloudonix, VoBIZ, Asterisk ARI) and WebRTC support.

**Tech stack:**
- **Backend:** Python 3.13 + FastAPI, SQLAlchemy (async), pgvector, ARQ (Redis queue)
- **Frontend:** Next.js 15 + React 19 + TypeScript + Tailwind CSS 4 + shadcn/ui + @xyflow/react (visual workflow builder)
- **Database:** PostgreSQL 17 with pgvector extension
- **Cache/Queue:** Redis 7
- **Storage:** MinIO (S3-compatible)
- **Voice Runtime:** Pipecat framework (git submodule at `pipecat/`)

---

## 2. Project Structure

```
scaiva/
├── api/                    # FastAPI backend
│   ├── app.py              # App entry point, mounts routes at /api/v1
│   ├── constants.py        # All env vars and config
│   ├── enums.py            # All enums (WorkflowRunMode, ToolCategory, etc.)
│   ├── routes/             # 28 route files (thin handlers)
│   ├── services/           # Domain logic (workflow, telephony, pipecat, auth, etc.)
│   ├── db/                 # SQLAlchemy models + DBClient (mixin pattern, 21 clients)
│   ├── schemas/            # Pydantic request/response models
│   ├── tasks/              # ARQ background jobs
│   ├── mcp_server/         # MCP (Model Context Protocol) server
│   ├── utils/              # Shared utilities
│   ├── alembic/            # 88 migration files
│   ├── tests/              # 88 test files
│   ├── pyproject.toml      # Python deps (uv)
│   └── .env                # Actual env vars (gitignored)
│
├── ui/                     # Next.js frontend
│   ├── src/app/            # App router pages (20+ routes)
│   ├── src/components/     # React components (flow builder, layout, telephony, etc.)
│   ├── src/client/         # Auto-generated API client from OpenAPI spec
│   ├── src/context/        # React contexts (AppConfig, Onboarding, etc.)
│   ├── src/hooks/          # Custom hooks
│   ├── src/lib/auth/       # Auth system (OSS JWT + Stack Auth for SaaS)
│   ├── src/middleware.ts   # Route protection middleware
│   └── package.json        # Node deps (pnpm)
│
├── scripts/                # 36 helper scripts (setup, migrate, deploy, etc.)
├── docs/                   # Mintlify documentation site
├── sdk/                    # Generated Python + TypeScript SDKs
├── pipecat/                # Pipecat framework (git submodule)
├── config/                 # CoTURN server config
├── deploy/                 # Deployment templates (nginx, TURN)
├── docker-compose.yaml     # Production (7 services)
├── docker-compose-local.yaml  # Local dev (postgres:5433, redis, minio)
├── AGENTS.md               # Master project doc for AI agents
└── CLAUDE.md               # Points to AGENTS.md
```

---

## 3. How to Run Locally

### Prerequisites
- Python 3.13+
- Node.js 20+ (check `.nvmrc`)
- Docker Desktop (for postgres, redis, minio)
- `uv` (Python package manager)
- `pnpm` (Node package manager)

### Step 1: Start infrastructure services
```bash
docker compose -f docker-compose-local.yaml up -d
# Starts: postgres (port 5433), redis (port 6379), minio (ports 9000/9001)
```

### Step 2: Backend setup
```bash
cd api
cp .env.example .env          # Edit with your values
uv sync                       # Install Python deps
python -m alembic upgrade head  # Run migrations
uvicorn api.app:app --reload --port 8000
```

### Step 3: Frontend setup
```bash
cd ui
cp .env.example .env          # Edit BACKEND_URL
pnpm install
pnpm dev                      # Starts on port 3010
```

### Step 4: Run tests
```bash
cd api
set -a && source .env.test && set +a
python -m pytest api/tests/ -v
```

---

## 4. Key Architecture Patterns

### Multi-Tenancy
All resources are scoped to `organization_id`. Every DB query must filter by org. The `get_user` dependency (in `api/services/auth/depends.py`) resolves the user and their selected organization.

### Route Layer Rule
Routes are thin: parse request, resolve auth + org, delegate to service, shape response. Domain logic lives in `services/`. DB access lives in `db/` clients. Never put business logic in route handlers.

### Workflow Engine
Frontend: Visual graph builder using React Flow (`ui/src/components/flow/`). Backend: `PipecatEngine` (`api/services/workflow/pipecat_engine.py`) orchestrates pipeline execution using the Pipecat framework. Workflows are versioned via `WorkflowDefinitionModel`.

### Telephony Provider System
8 providers in `api/services/telephony/providers/`: Twilio, Telnyx, Plivo, Vonage, Acefone, Cloudonix, VoBIZ, ARI (Asterisk). Factory pattern resolves provider from stored config.

### Background Processing (ARQ)
Redis-based queue for post-call tasks: S3 uploads, integration execution, campaign batch processing, knowledge base document processing. Worker config in `api/tasks/arq.py`.

### Cross-Worker State Sync
`WorkerSyncManager` (`api/services/worker_sync/`) uses Redis pub/sub to propagate in-memory state (like Langfuse credentials) across multiple FastAPI worker processes.

### Database
- SQLAlchemy async with pgvector for vector embeddings
- `DBClient` class inherits from 21 specialized client classes (mixin pattern)
- 88 Alembic migrations in `api/alembic/versions/`
- Organizations, workflows, campaigns, telephony configs, tools, knowledge base, API keys

### Authentication
- **OSS mode:** Local email/password with JWT tokens (cookie: `scaiva_auth_token`)
- **SaaS mode:** Stack Auth provider
- **API access:** API key via `X-API-Key` header

---

## 5. Current State (Uncommitted Changes)

### Modified files (10):
| File | Change |
|---|---|
| `.gitignore` | 1 line added |
| `api/.env.example` | Minor env var updates |
| `api/.env.test.example` | Minor env var updates |
| `api/routes/auth.py` | +13/-2 lines (auth route changes) |
| `docker-compose-local.yaml` | 1 line changed |
| `docker-compose.yaml` | +6 lines |
| `ui/package.json` | 1 dependency version change |
| `ui/src/app/api/auth/oss/route.ts` | Minor auth changes |
| `ui/src/app/api/auth/session/route.ts` | Minor session changes |
| `ui/src/app/layout.tsx` | Layout change |

### New untracked files (10):
| File | Purpose |
|---|---|
| `api/utils/rate_limit.py` | Rate limiting utility |
| `api/tests/test_rate_limit.py` | Tests for rate limiting |
| `run_backend.bat` | Windows batch script to start backend |
| `run_backend.ps1` | PowerShell script to start backend |
| `run_ui.bat` | Windows batch script to start UI |
| `scripts/deploy_scaiva_remote.sh` | Remote deployment script |
| `scripts/deploy_scaiva_runner.ps1` | Remote deployment (PowerShell) |
| `scripts/start_ui.vbs` | VBScript to start UI |
| `test_db.py` | DB test script |
| `ui/pnpm-lock.yaml` | pnpm lockfile |

---

## 6. Critical Files to Know

### Backend
- `api/app.py` — FastAPI app entry point, route mounting, CORS, lifespan
- `api/constants.py` — All environment variables and config values
- `api/enums.py` — All enums (WorkflowRunMode, ToolCategory, WorkflowStatus, etc.)
- `api/db/models.py` — All SQLAlchemy models (1298 lines)
- `api/db/db_client.py` — Unified DB client (mixin of 21 clients)
- `api/services/workflow/pipecat_engine.py` — Core pipeline orchestration
- `api/services/workflow/workflow_graph.py` — Workflow graph parsing
- `api/services/pipecat/run_pipeline.py` — Pipecat pipeline runtime (835 lines)
- `api/services/telephony/` — Full telephony subsystem
- `api/tasks/arq.py` — Background job configuration
- `api/conftest.py` — Test infrastructure (373 lines)

### Frontend
- `ui/src/app/layout.tsx` — Root layout
- `ui/src/middleware.ts` — Route protection
- `ui/src/components/flow/` — Workflow visual builder (React Flow)
- `ui/src/client/sdk.gen.ts` — Auto-generated API client
- `ui/src/lib/auth/` — Auth system
- `ui/next.config.ts` — Next.js config (API proxy, Sentry, PostHog)

### Config
- `docker-compose.yaml` — Production stack
- `docker-compose-local.yaml` — Local dev services
- `api/pyproject.toml` — Python dependencies
- `ui/package.json` — Node dependencies
- `.github/workflows/` — CI/CD (api-tests, docker-image, release)

---

## 7. Development Conventions

1. **Python:** Strict typing, no `any`, async/await throughout. Use `uv` for package management.
2. **TypeScript:** Strict mode, no `any`, no `// @ts-ignore`. Path alias `@/*` -> `./src/*`.
3. **CSS:** Tailwind CSS 4, shadcn/ui components.
4. **State management:** Zustand (frontend).
5. **API client:** Auto-generated from OpenAPI spec via `@hey-api/openapi-ts`.
6. **Database changes:** Always create Alembic migrations (`./scripts/makemigrate.sh "description"`).
7. **Commits:** Conventional commits: feat / fix / chore / docs.
8. **Organization scoping:** ALL resources must be scoped to `organization_id`. Never skip this.
9. **Route handlers:** Keep thin. Domain logic goes in `services/`.
10. **Tests:** 88 test files, transaction-based isolation per test. Run with `pytest`.

---

## 8. Git Status

```
Branch: main (clean, ahead of origin)
Last commit: 1fcc3fe "Rename Dograh → SCAIVA (S2 Connects AI Voice Agent)"
```

**Recent feature commits:**
- `98d2b24` — Add Sarvam LLM, update Sarvam STT models, expose usage_info
- `fcb7004` — Create tools using MCP
- `5c29b6e` — Add MCP guides for various topics
- `c586d02` — Abort immediately on max call duration exceed
- `78ba62e` — Banner if API is not reachable

---

## 9. Known Issues / Notes

1. The project was recently renamed from **Dograh** to **SCAIVA**. Some internal references (class names, package names, import paths) may still use "dograh" — this is intentional for backwards compatibility with DB records and the Pipecat submodule.
2. The `pipecat/` directory is a git submodule from `dograh-hq/pipecat`. It is the core voice runtime framework.
3. There are 10 modified + 10 untracked files that have NOT been committed. Review and commit them as appropriate.
4. The `api/.env` and `ui/.env` files contain actual secrets and are gitignored. Never commit them.
5. The SDK (`sdk/`) is auto-generated from the backend OpenAPI spec. Regenerate with `./scripts/generate_sdk.sh`.
6. Tests use a separate `_test` database. The test DB is created and migrated automatically via `conftest.py`.

---

## 10. If You're Starting Fresh

1. Read `AGENTS.md` for project conventions
2. Read `docs/contribution/setup.mdx` for contributor setup
3. Start local services: `docker compose -f docker-compose-local.yaml up -d`
4. Set up backend: `cd api && cp .env.example .env && uv sync && python -m alembic upgrade head`
5. Set up frontend: `cd ui && cp .env.example .env && pnpm install && pnpm dev`
6. Run tests: `cd api && python -m pytest api/tests/ -v`
7. The API docs are auto-generated at `http://localhost:8000/docs` (Swagger UI)

---

*This document is the single source of truth for continuing development on SCAIVA.*
