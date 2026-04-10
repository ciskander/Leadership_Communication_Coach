"""
api/auth.py — Session management, user CRUD, and OAuth user resolution.
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..auth.models import Session, UserAuth, UserCredential
from ..auth.sqlite_db import get_conn

SESSION_COOKIE_NAME = "sid"
SESSION_TTL_DAYS = 7
_SECRET = os.environ.get("SESSION_SECRET", "change-me")
_SERIALIZER = URLSafeTimedSerializer(_SECRET, salt="session")
ADMIN_EMAILS: set[str] = {
    e.strip().lower()
    for e in os.getenv("ADMIN_EMAILS", "").split(",")
    if e.strip()
}


# ── Session helpers ───────────────────────────────────────────────────────────

def create_session(user_id: str) -> str:
    raw_id = secrets.token_hex(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (session_id, user_id, expires_at) VALUES (%s, %s, %s)",
                (raw_id, user_id, expires_at.isoformat()),
            )
        conn.commit()
    return _SERIALIZER.dumps(raw_id)


def resolve_session(signed_token: str) -> Optional[UserAuth]:
    try:
        raw_id = _SERIALIZER.loads(signed_token, max_age=SESSION_TTL_DAYS * 86_400)
    except (BadSignature, SignatureExpired):
        return None

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT s.session_id, s.user_id, u.id, u.email, u.display_name,
                       u.role, u.oauth_provider, u.oauth_sub, u.coach_id,
                       u.airtable_user_record_id, u.profile_photo_url,
                       u.created_at, u.last_login
                FROM sessions s
                JOIN users_auth u ON u.id = s.user_id
                WHERE s.session_id = %s AND s.expires_at > %s
                """,
                (raw_id, datetime.now(timezone.utc).isoformat()),
            )
            row = cur.fetchone()

    if not row:
        return None

    new_expires = datetime.now(timezone.utc) + timedelta(days=SESSION_TTL_DAYS)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET expires_at = %s WHERE session_id = %s",
                (new_expires.isoformat(), raw_id),
            )
        conn.commit()

    return _user_from_row(row)


def delete_session(signed_token: str) -> None:
    try:
        raw_id = _SERIALIZER.loads(signed_token, max_age=SESSION_TTL_DAYS * 86_400)
    except (BadSignature, SignatureExpired):
        return
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE session_id = %s", (raw_id,))
        conn.commit()


# ── User helpers ──────────────────────────────────────────────────────────────

def get_user_by_id(user_id: str) -> Optional[UserAuth]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users_auth WHERE id = %s", (user_id,))
            row = cur.fetchone()
    return UserAuth.from_row(row) if row else None


def get_user_by_email(email: str) -> Optional[UserAuth]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users_auth WHERE email = %s", (email.lower(),))
            row = cur.fetchone()
    return UserAuth.from_row(row) if row else None


def get_user_by_oauth(provider: str, sub: str) -> Optional[UserAuth]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users_auth WHERE oauth_provider = %s AND oauth_sub = %s",
                (provider, sub),
            )
            row = cur.fetchone()
    return UserAuth.from_row(row) if row else None


def create_user(
    *,
    email: str,
    display_name: Optional[str],
    role: str,
    oauth_provider: Optional[str] = None,
    oauth_sub: Optional[str] = None,
    coach_id: Optional[str] = None,
    airtable_user_record_id: Optional[str] = None,
    profile_photo_url: Optional[str] = None,
) -> UserAuth:
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users_auth
                  (id, email, display_name, role, oauth_provider, oauth_sub,
                   coach_id, airtable_user_record_id, profile_photo_url,
                   created_at, last_login)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id, email.lower(), display_name, role,
                    oauth_provider, oauth_sub,
                    coach_id, airtable_user_record_id, profile_photo_url,
                    now, now,
                ),
            )
        conn.commit()
    return get_user_by_id(user_id)  # type: ignore[return-value]


def update_last_login(user_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users_auth SET last_login = %s WHERE id = %s",
                (datetime.now(timezone.utc).isoformat(), user_id),
            )
        conn.commit()


def update_profile_photo_url(user_id: str, photo_url: Optional[str]) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users_auth SET profile_photo_url = %s WHERE id = %s",
                (photo_url, user_id),
            )
        conn.commit()


def update_airtable_record_id(user_id: str, record_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users_auth SET airtable_user_record_id = %s WHERE id = %s",
                (record_id, user_id),
            )
        conn.commit()


def promote_to_coach(user_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users_auth SET role = 'coach' WHERE id = %s", (user_id,)
            )
        conn.commit()


def list_all_users() -> list[UserAuth]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM users_auth ORDER BY created_at DESC")
            rows = cur.fetchall()
    return [UserAuth.from_row(r) for r in rows]


def list_coachees_for_coach(coach_id: str) -> list[UserAuth]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users_auth WHERE coach_id = %s ORDER BY created_at DESC",
                (coach_id,),
            )
            rows = cur.fetchall()
    return [UserAuth.from_row(r) for r in rows]


# ── Landing URL per role ──────────────────────────────────────────────────────

ROLE_LANDING: dict[str, str] = {
    "coach": "/coach",
    "coachee": "/client",
    "admin": "/admin",
}


def landing_url_for(role: str) -> str:
    return ROLE_LANDING.get(role, "/")


# ── Credential helpers ────────────────────────────────────────────────────────

def get_credential(provider: str, provider_sub: str) -> Optional[UserCredential]:
    """Look up a credential by provider + subject ID."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM user_credentials WHERE provider = %s AND provider_sub = %s",
                (provider, provider_sub),
            )
            row = cur.fetchone()
    return UserCredential.from_row(row) if row else None


def get_credential_by_user(user_id: str, provider: str) -> Optional[UserCredential]:
    """Look up a credential for a specific user + provider."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM user_credentials WHERE user_id = %s AND provider = %s",
                (user_id, provider),
            )
            row = cur.fetchone()
    return UserCredential.from_row(row) if row else None


def create_credential(
    *,
    user_id: str,
    provider: str,
    provider_sub: Optional[str] = None,
    password_hash: Optional[str] = None,
    email_verified: bool = False,
) -> UserCredential:
    cred_id = str(uuid.uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO user_credentials
                  (id, user_id, provider, provider_sub, password_hash, email_verified)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (cred_id, user_id, provider, provider_sub, password_hash, email_verified),
            )
        conn.commit()
    return get_credential_by_user(user_id, provider)  # type: ignore[return-value]


def set_email_verified(credential_id: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE user_credentials SET email_verified = TRUE WHERE id = %s",
                (credential_id,),
            )
        conn.commit()


def update_password_hash(credential_id: str, new_hash: str) -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE user_credentials SET password_hash = %s WHERE id = %s",
                (new_hash, credential_id),
            )
        conn.commit()


# ── Private helpers ───────────────────────────────────────────────────────────

def _user_from_row(row) -> UserAuth:
    return UserAuth(
        id=row["id"],
        email=row["email"],
        role=row["role"],
        oauth_provider=row["oauth_provider"],
        oauth_sub=row["oauth_sub"],
        display_name=row["display_name"],
        coach_id=row["coach_id"],
        airtable_user_record_id=row["airtable_user_record_id"],
        profile_photo_url=row.get("profile_photo_url"),
        created_at=row["created_at"],
        last_login=row["last_login"],
    )