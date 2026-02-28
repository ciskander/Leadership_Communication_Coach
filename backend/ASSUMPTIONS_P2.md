# Prompt 2 Assumptions

1. **OAuth provider — Google only** via `authlib` (Starlette integration). PKCE not
   required for server-side flow; `state` param carries an optional `invite_token`.

2. **Queue library — Celery + Redis** (matches `REDIS_URL` already in config.py and
   `redis>=5.0.0` in Prompt 1 requirements). Worker process is launched with
   `celery -A backend.queue.celery_app worker`.

3. **Session cookie** — signed with `itsdangerous.URLSafeTimedSerializer` using
   `SESSION_SECRET`. Stored as HTTP-only cookie named `sid`. Sliding 7-day TTL
   is implemented by refreshing `expires_at` on each authenticated request.

4. **File extraction** — `.txt`/`.vtt`/`.srt` files are read as plain text; `.docx`
   uses `python-docx`; `.pdf` uses `pdfplumber`. The extracted text is written into
   the Airtable `Transcript (extracted)` field before the job is enqueued, matching
   the assumption in Prompt 1's ASSUMPTIONS.md.

5. **`ADMIN_EMAILS`** is a comma-separated env var. On first login (no invite token),
   if the Google email is in that list, the user is created with role `admin`; otherwise
   the login is rejected (only invited coachees and known admins can sign up).
