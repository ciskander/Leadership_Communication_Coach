# Leadership Coach — MVP

AI-powered leadership communication coaching, grounded in real meeting transcripts.

---

## Architecture Overview

The system is a three-tier web application. The **frontend** is a Next.js 14 (App Router) single-page application that handles role-aware routing (coachee, coach, admin), transcript uploads, run status polling, and coaching card display. It communicates exclusively with the backend API over HTTP and stores no user state locally.

The **backend** is a FastAPI application (Python 3.11+) that exposes a RESTful API, manages authentication via Google OAuth + session cookies backed by SQLite, and orchestrates all domain logic. When a user submits a transcript for analysis, the API enqueues an async job to Redis via Celery. A separate **worker** process picks up jobs, calls OpenAI GPT-4o with a structured coaching prompt, validates the response through a strict Gate-1 JSON schema check, and writes coaching results back to Airtable.

**Airtable** serves as the primary data store for all domain records (transcripts, runs, experiments, baseline packs, users). **Redis** is used solely as a Celery message broker and result backend. An **SQLite database** (`auth.db`) stores session tokens and user auth metadata locally. The system integrates with **Make (Integromat)** for event-driven webhooks (see Make Blueprint Mapping below).

---

## Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.11+ | Backend + worker |
| Node.js | 18+ | Frontend |
| Redis | 6+ | Message broker |
| Airtable account | — | Data store |
| Google Cloud project | — | OAuth 2.0 |
| OpenAI API key | — | GPT-4o access |
| Make (Integromat) account | — | Webhook automation (optional) |

---

## Environment Variables

Copy `.env.example` to `.env` and fill in all values.

| Variable | Required | Description |
|---|---|---|
| `AIRTABLE_TOKEN` | ✅ | Airtable personal access token (PAT) |
| `AIRTABLE_BASE_ID` | ✅ | Airtable base ID (starts with `app`) |
| `OPENAI_API_KEY` | ✅ | OpenAI API key |
| `OPENAI_MODEL` | — | Model to use (default: `gpt-4o`) |
| `REDIS_URL` | ✅ | Redis connection URL |
| `OAUTH_CLIENT_ID` | ✅ | Google OAuth 2.0 client ID |
| `OAUTH_CLIENT_SECRET` | ✅ | Google OAuth 2.0 client secret |
| `OAUTH_REDIRECT_URL` | ✅ | OAuth callback URL (must match Google console) |
| `SESSION_SECRET` | ✅ | Random secret for session signing (32+ bytes hex) |
| `ADMIN_EMAILS` | — | Comma-separated emails that get `admin` role on first login |
| `FRONTEND_BASE_URL` | ✅ | Frontend origin, e.g. `http://localhost:3000` |
| `CORS_ORIGINS` | ✅ | Comma-separated allowed CORS origins |
| `SQLITE_DB_PATH` | — | Path to auth SQLite DB (default: `auth.db`) |
| `COOKIE_SECURE` | — | Set `false` for local HTTP dev (default: `true`) |
| `NEXT_PUBLIC_API_URL` | ✅ | Backend URL as seen by the browser |

---

## Setup

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy and fill in env vars
cp ../.env.example ../.env

# Run database migration (creates auth.db)
python -m backend.auth.sqlite_db

# Start API server (development)
uvicorn backend.main:app --reload --port 8000
```

### 2. Worker

In a separate terminal (same virtualenv):

```bash
source .venv/bin/activate
celery -A backend.queue.celery_app worker --loglevel=info
```

### 3. Redis

```bash
# macOS (Homebrew)
brew services start redis

# Linux
sudo systemctl start redis

# Docker
docker run -d -p 6379:6379 redis:7-alpine
```

### 4. Frontend

```bash
cd frontend
npm install

# Development server
npm run dev          # http://localhost:3000
```

---

## OAuth Provider Configuration (Google)

1. Go to [Google Cloud Console](https://console.cloud.google.com/) → APIs & Services → Credentials.
2. Create an **OAuth 2.0 Client ID** (Web application).
3. Add `http://localhost:8000/api/auth/callback` to **Authorised redirect URIs**.
4. For production, also add your production callback URL.
5. Copy **Client ID** and **Client Secret** to `.env`.

---

## Airtable Setup

1. Create a new Airtable base (or use an existing one).
2. Copy your base ID from the URL: `https://airtable.com/appXXXXXX/...`
3. Generate a Personal Access Token (PAT) with `data:records:read` and `data:records:write` scopes on your base.
4. Run the migration to apply the required schema:

```bash
# Review the diff first
cat backend/airtable_migration_diff.md

# Apply via the Airtable web UI or CLI
# The diff describes all required tables, fields, and field types.
```

Key tables required: `Users`, `Transcripts`, `Run Requests`, `Runs`, `Baseline Packs`, `Experiments`, `Experiment Events`.

---

## Running Locally

Start all services in order:

```bash
# Terminal 1 — Redis
docker run -d -p 6379:6379 redis:7-alpine

# Terminal 2 — Backend API
cd backend && uvicorn backend.main:app --reload --port 8000

# Terminal 3 — Celery Worker
cd backend && celery -A backend.queue.celery_app worker --loglevel=info

# Terminal 4 — Frontend
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and sign in with Google.

---

## Running Tests

```bash
cd backend
pip install -r requirements.txt
pip install pytest pytest-asyncio httpx

# All tests
pytest tests/ -v

# Specific test files
pytest tests/test_transcript_parser.py -v
pytest tests/test_gate1_validator.py -v
pytest tests/test_idempotency.py -v
pytest tests/test_workers.py -v
pytest tests/test_api_auth.py -v

# With coverage
pip install pytest-cov
pytest tests/ --cov=backend --cov-report=term-missing
```

Tests use mocked Airtable and OpenAI — no real API calls are made.

---

## Docker Compose (Full Stack)

```bash
# Build and start all services
cp .env.example .env   # fill in real values
docker-compose up --build

# Stop
docker-compose down
```

Services exposed:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Redis: localhost:6379

SQLite data is persisted in the `sqlite_data` Docker volume across restarts.

---

## Make Blueprint Mapping

The following Make (Integromat) automations map to backend components:

| Blueprint File | Description | Backend Component |
|---|---|---|
| `A1_-_Baseline_Pack_Builder_blueprint.json` | Assembles 3 transcripts into a baseline pack job | `POST /api/baseline_packs` → `queue/tasks.py:enqueue_baseline_pack_build` |
| `A2_-_Build_Baseline_Pack_blueprint.json` | Triggers baseline pack analysis run | `POST /api/baseline_packs/{id}/build` → `core/workers.py:process_baseline_pack` |
| `D1_-_Create_attempt_event_after_each_qualifying_run_blueprint.json` | Creates experiment attempt event after each run with active experiment | `core/workers.py` (post-run experiment detection logic) |
| `E1_-_Instantiate_an_experiment_from_a_baseline_pack_run_blueprint.json` | Instantiates experiment from baseline coaching output | `core/workers.py:_instantiate_experiment_if_needed` |
| `R1_-_Process_Queued_Run_Requests__single_meeting__blueprint.json` | Picks up queued single-meeting run requests | `queue/tasks.py:enqueue_single_meeting` → `core/workers.py:process_single_meeting_analysis` |
| `S1_Worker_Webhook_Gate1__no_evidence_span_renumbering__blueprint.json` | Gate1 webhook (no span renumbering variant) | `core/gate1_validator.py:validate` |
| `S3_Worker_Webhook_Baseline_Pack_blueprint.json` | Baseline pack webhook processing | `core/workers.py:process_baseline_pack` |

The Make automations serve as an alternative/companion trigger mechanism. The backend also supports direct API-triggered runs without Make.

---

## Project Structure

```
├── backend/
│   ├── api/            # FastAPI routes, DTOs, auth middleware
│   ├── auth/           # OAuth, session, SQLite models
│   ├── core/           # Engine: transcript parser, Gate1, prompt builder, workers
│   ├── queue/          # Celery app, tasks
│   └── main.py
├── frontend/
│   └── src/
│       ├── app/        # Next.js App Router pages (client, coach, admin)
│       ├── components/ # CoachingCard, PatternSnapshot, ExperimentTracker, etc.
│       ├── hooks/      # useAuth, useRunPoller, useActiveExperiment
│       └── lib/        # api.ts, types.ts, auth.ts
├── backend/tests/      # pytest tests (no real API calls)
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
└── .env.example
```
