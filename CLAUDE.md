# Leadership Communication Coach

## Tech Stack
- **Frontend**: Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, Recharts
- **Backend**: FastAPI (Python), SQLite (auth), Celery (async tasks)
- **Auth**: Google OAuth via authlib, session-based with signed tokens (7-day TTL)
- **Roles**: `coachee`, `coach`, `admin` — enforced by `RoleGuard` component

## Project Structure

### Frontend (`frontend/src/`)
- `app/` — Next.js App Router pages, role-based routing:
  - `client/` — Coachee pages (dashboard, analyze, baseline, experiment, progress, runs)
  - `coach/` — Coach pages (dashboard, coachees/[id], analyze)
  - `admin/` — Admin dashboard (user management)
  - `auth/` — OAuth callback
  - `page.tsx` — Login page
- `components/` — Shared UI (Layout/Navbar, Layout/Sidebar, CoachingCard, TranscriptUpload, ExperimentTracker, etc.)
- `config/strings.ts` — Centralized UI strings as `STRINGS` object. All user-facing text goes here. Components import and use via dot notation.

### Backend (`backend/`)
- `routes_*.py` — API routes organized by resource (auth, transcripts, runs, coachee, experiments, coach, admin)
- Celery for async analysis jobs
- Pure Python dataclasses as models (no ORM)

## Conventions
- All hardcoded UI strings must be in `config/strings.ts`
- Tailwind for styling (emerald, stone, rose, blue palette)
- Role-based access via `RoleGuard` component wrapping pages

## Coachee User Journey (current)
1. Login via Google OAuth
2. Create a Baseline Pack (upload multiple meeting transcripts for initial assessment)
3. Analyze individual meetings (upload transcript → AI analysis)
4. Accept and track Experiments (behavioral changes suggested by AI)
5. View Progress over time

The client dashboard shows a visual journey tracker with these steps. There is **no formal onboarding/tutorial system** — the app currently relies on the journey tracker and contextual CTAs.

## Active Branch
- `claude/user-profile-photo-5W5Ej` — current feature branch
