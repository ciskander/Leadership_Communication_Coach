"""
auth/token_utils.py — Invite token generation and validation helpers.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from .sqlite_db import get_conn


TOKEN_TTL_DAYS: int = 7
TOKEN_BYTES: int = 32


def generate_invite_token(coach_id: str, role: str = "coachee") -> str:
    """Create and persist a new invite token. Returns the raw token string."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO invite_tokens (token, coach_id, role, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token, coach_id, role, expires_at.isoformat()),
        )
        conn.commit()
    return token


def validate_invite_token(token: str) -> Optional[dict]:
    """
    Check the token. Returns a dict with coach_id and role if valid,
    or None if expired / already used / not found.
    """
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM invite_tokens WHERE token = ?", (token,)
        ).fetchone()

    if not row:
        return None
    if row["used_by"] is not None:
        return None  # already used

    expires_at = datetime.fromisoformat(str(row["expires_at"]))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        return None

    return {"coach_id": row["coach_id"], "role": row["role"]}


def consume_invite_token(token: str, used_by_user_id: str) -> None:
    """Mark the token as consumed."""
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE invite_tokens
            SET used_by = ?, used_at = ?
            WHERE token = ?
            """,
            (used_by_user_id, datetime.now(timezone.utc).isoformat(), token),
        )
        conn.commit()
