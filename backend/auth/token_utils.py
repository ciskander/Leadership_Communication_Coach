"""
auth/token_utils.py — Invite token and email token generation/validation helpers.
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
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO invite_tokens (token, coach_id, role, expires_at)
                VALUES (%s, %s, %s, %s)
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
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM invite_tokens WHERE token = %s", (token,)
            )
            row = cur.fetchone()

    if not row:
        return None
    if row["used_by"] is not None:
        return None

    expires_at = datetime.fromisoformat(str(row["expires_at"]))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        return None

    return {"coach_id": row["coach_id"], "role": row["role"]}


def consume_invite_token(token: str, used_by_user_id: str) -> None:
    """Mark the token as consumed."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE invite_tokens
                SET used_by = %s, used_at = %s
                WHERE token = %s
                """,
                (used_by_user_id, datetime.now(timezone.utc).isoformat(), token),
            )
        conn.commit()


# ── Email tokens (verification + password reset) ────────────────────────────

def generate_email_token(user_id: str, token_type: str, ttl_hours: int = 1) -> str:
    """Create and persist an email verification or password reset token."""
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO email_tokens (token, user_id, token_type, expires_at)
                VALUES (%s, %s, %s, %s)
                """,
                (token, user_id, token_type, expires_at.isoformat()),
            )
        conn.commit()
    return token


def validate_email_token(token: str, expected_type: str) -> Optional[dict]:
    """
    Validate an email token. Returns {user_id} if valid and unused,
    or None if expired / wrong type / already used / not found.
    """
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM email_tokens WHERE token = %s", (token,))
            row = cur.fetchone()

    if not row:
        return None
    if row["token_type"] != expected_type:
        return None
    if row["used_at"] is not None:
        return None

    expires_at = datetime.fromisoformat(str(row["expires_at"]))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        return None

    return {"user_id": row["user_id"]}


def consume_email_token(token: str) -> None:
    """Mark an email token as used."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE email_tokens SET used_at = %s WHERE token = %s",
                (datetime.now(timezone.utc).isoformat(), token),
            )
        conn.commit()