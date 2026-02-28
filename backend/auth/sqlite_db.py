"""
auth/sqlite_db.py — SQLite schema bootstrap and shared connection helper.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Generator

DB_PATH = os.getenv("SQLITE_DB_PATH", "auth.db")

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
    created_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login       DATETIME
);
"""

_CREATE_SESSIONS = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id  TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users_auth(id),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at  DATETIME NOT NULL
);
"""

_CREATE_INVITE_TOKENS = """
CREATE TABLE IF NOT EXISTS invite_tokens (
    token       TEXT PRIMARY KEY,
    coach_id    TEXT NOT NULL REFERENCES users_auth(id),
    role        TEXT NOT NULL DEFAULT 'coachee',
    used_by     TEXT REFERENCES users_auth(id),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at  DATETIME NOT NULL,
    used_at     DATETIME
);
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);",
    "CREATE INDEX IF NOT EXISTS idx_users_oauth ON users_auth(oauth_provider, oauth_sub);",
    "CREATE INDEX IF NOT EXISTS idx_invite_token ON invite_tokens(token);",
]


def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    with get_conn() as conn:
        conn.execute(_CREATE_USERS_AUTH)
        conn.execute(_CREATE_SESSIONS)
        conn.execute(_CREATE_INVITE_TOKENS)
        for idx in _INDEXES:
            conn.execute(idx)
        conn.commit()


@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    """Yield an autocommit-safe connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    try:
        yield conn
    finally:
        conn.close()
