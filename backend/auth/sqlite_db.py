"""
auth/sqlite_db.py — PostgreSQL schema bootstrap and shared connection helper.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ["DATABASE_URL"]

_CREATE_USERS_AUTH = """
CREATE TABLE IF NOT EXISTS users_auth (
    id               TEXT PRIMARY KEY,
    email            TEXT UNIQUE NOT NULL,
    display_name     TEXT,
    role             TEXT NOT NULL CHECK(role IN ('admin','coach','coachee')),
    coach_id         TEXT REFERENCES users_auth(id),
    oauth_provider   TEXT NOT NULL,
    oauth_sub        TEXT NOT NULL,
    airtable_user_record_id TEXT,
    profile_photo_url TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    last_login       TIMESTAMPTZ
);
"""

_CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users_auth(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL
);
"""

_CREATE_INVITE_TOKENS = """
CREATE TABLE IF NOT EXISTS invite_tokens (
    token       TEXT PRIMARY KEY,
    coach_id    TEXT NOT NULL REFERENCES users_auth(id),
    role        TEXT NOT NULL DEFAULT 'coachee',
    used_by     TEXT REFERENCES users_auth(id),
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL,
    used_at     TIMESTAMPTZ
);
"""

_MIGRATIONS = [
    "ALTER TABLE users_auth ADD COLUMN IF NOT EXISTS profile_photo_url TEXT;",
]

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_users_oauth ON users_auth(oauth_provider, oauth_sub);",
    "CREATE INDEX IF NOT EXISTS idx_invite_token ON invite_tokens(token);",
]


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_USERS_AUTH)
            cur.execute(_CREATE_SESSIONS)
            cur.execute(_CREATE_INVITE_TOKENS)
            for mig in _MIGRATIONS:
                cur.execute(mig)
            for idx in _INDEXES:
                cur.execute(idx)
        conn.commit()


@contextmanager
def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    """Yield a connection with RealDictCursor row factory."""
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()