"""
api/routes_auth.py — OAuth login/callback/logout + invite generation.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth.models import UserAuth
from ..auth.token_utils import consume_invite_token, validate_invite_token
from .auth import (
    ADMIN_EMAILS,
    SESSION_COOKIE_NAME,
    SESSION_TTL_DAYS,
    create_session,
    create_user,
    delete_session,
    get_user_by_email,
    get_user_by_oauth,
    landing_url_for,
    update_last_login,
    update_airtable_record_id,
)
from .dependencies import get_current_user
from .dto import InviteResponse, MeResponse
from .errors import forbidden, invite_already_used, invite_expired
from ..auth.token_utils import generate_invite_token

router = APIRouter()

# ── OAuth configuration ───────────────────────────────────────────────────────
oauth = OAuth()
oauth.register(
    name="google",
    client_id=os.environ.get("OAUTH_CLIENT_ID", ""),
    client_secret=os.environ.get("OAUTH_CLIENT_SECRET", ""),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

_REDIRECT_URL = os.environ.get("OAUTH_REDIRECT_URL", "http://localhost:8000/api/auth/callback")
_FRONTEND_BASE = os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sync_airtable_user(user: UserAuth) -> None:
    """Best-effort sync user to Airtable users table."""
    try:
        from ..core.airtable_client import AirtableClient
        client = AirtableClient()
        if user.airtable_user_record_id:
            client.update_record(
                "users",
                user.airtable_user_record_id,
                {
                    "Email": user.email,
                    "Display Name": user.display_name,
                    "Role": user.role,
                },
            )
        else:
            rec = client.create_record(
                "users",
                {
                    "Email": user.email,
                    "Display Name": user.display_name,
                    "Role": user.role,
                    "Auth ID": user.id,
                },
            )
            update_airtable_record_id(user.id, rec["id"])
    except Exception:
        pass  # Non-blocking; Airtable sync failure should not break login


def _set_session_cookie(response: RedirectResponse, signed_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=signed_token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=SESSION_TTL_DAYS * 86_400,
        path="/",
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/api/auth/login")
async def login(request: Request, invite_token: Optional[str] = None):
    """Redirect to Google OAuth. Optionally carry invite_token in state."""
    state_data = json.dumps({"invite_token": invite_token}) if invite_token else None
    redirect_uri = _REDIRECT_URL
    return await oauth.google.authorize_redirect(
        request, redirect_uri, state=state_data
    )


@router.get("/api/auth/callback")
async def callback(request: Request):
    """Handle Google OAuth callback."""
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo") or await oauth.google.userinfo(token=token)

    email: str = (user_info.get("email") or "").lower()
    sub: str = user_info.get("sub", "")
    display_name: Optional[str] = user_info.get("name")

    # Parse state for invite_token
    raw_state = request.query_params.get("state", "")
    invite_token: Optional[str] = None
    if raw_state:
        try:
            invite_token = json.loads(raw_state).get("invite_token")
        except (json.JSONDecodeError, AttributeError):
            pass

    # ── Case 1: existing user ────────────────────────────────────────────────
    existing = get_user_by_oauth("google", sub)
    if existing:
        update_last_login(existing.id)
        _sync_airtable_user(existing)
        signed = create_session(existing.id)
        resp = RedirectResponse(url=_FRONTEND_BASE + landing_url_for(existing.role))
        _set_session_cookie(resp, signed)
        return resp

    # ── Case 2: invite-based signup ──────────────────────────────────────────
    if invite_token:
        token_data = validate_invite_token(invite_token)
        if token_data is None:
            # Determine if expired vs already used for better UX
            from ..auth.sqlite_db import get_conn as _gc
            with _gc() as c:
                row = c.execute("SELECT * FROM invite_tokens WHERE token=?", (invite_token,)).fetchone()
            if row and row["used_by"]:
                return invite_already_used()
            return invite_expired()

        new_user = create_user(
            email=email,
            display_name=display_name,
            role=token_data["role"],
            oauth_provider="google",
            oauth_sub=sub,
            coach_id=token_data["coach_id"],
        )
        consume_invite_token(invite_token, new_user.id)
        _sync_airtable_user(new_user)
        signed = create_session(new_user.id)
        resp = RedirectResponse(url=_FRONTEND_BASE + landing_url_for(new_user.role))
        _set_session_cookie(resp, signed)
        return resp

    # ── Case 3: admin signup ─────────────────────────────────────────────────
    if email in ADMIN_EMAILS:
        new_user = create_user(
            email=email,
            display_name=display_name,
            role="admin",
            oauth_provider="google",
            oauth_sub=sub,
        )
        _sync_airtable_user(new_user)
        signed = create_session(new_user.id)
        resp = RedirectResponse(url=_FRONTEND_BASE + landing_url_for("admin"))
        _set_session_cookie(resp, signed)
        return resp

    # ── No valid path ────────────────────────────────────────────────────────
    return forbidden("Access denied. Please use an invite link to register.")


@router.post("/api/auth/logout")
async def logout(
    sid: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    if sid:
        delete_session(sid)
    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie(key=SESSION_COOKIE_NAME)
    return resp


@router.get("/api/me", response_model=MeResponse)
async def me(user: UserAuth = Depends(get_current_user)):
    return MeResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        coach_id=user.coach_id,
        airtable_user_record_id=user.airtable_user_record_id,
        last_login=user.last_login,
    )


@router.post("/api/invites/coachee", response_model=InviteResponse)
async def create_coachee_invite(
    user: UserAuth = Depends(get_current_user),
):
    """Generate a single-use invite link for a coachee. Coach-only."""
    if user.role not in ("coach", "admin"):
        raise HTTPException(status_code=403, detail="Only coaches can generate invites.")
    token = generate_invite_token(user.id, role="coachee")
    invite_url = f"{_FRONTEND_BASE}/register?invite_token={token}"
    return InviteResponse(invite_url=invite_url, token=token)
