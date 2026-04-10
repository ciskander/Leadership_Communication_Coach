"""
api/routes_auth.py — OAuth login/callback/logout, email/password auth, invite generation.
"""
from __future__ import annotations

import collections
import json
import logging
import os
import time
from typing import Optional

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from ..auth.models import UserAuth
from ..auth.password import hash_password, validate_password_strength, verify_password
from ..auth.token_utils import (
    consume_email_token,
    consume_invite_token,
    generate_email_token,
    generate_invite_token,
    validate_email_token,
    validate_invite_token,
)
from .auth import (
    ADMIN_EMAILS,
    SESSION_COOKIE_NAME,
    SESSION_TTL_DAYS,
    create_credential,
    create_session,
    create_user,
    delete_session,
    get_credential,
    get_credential_by_user,
    get_user_by_email,
    get_user_by_oauth,
    landing_url_for,
    set_email_verified,
    update_airtable_record_id,
    update_last_login,
    update_password_hash,
    update_profile_photo_url,
)
from .dependencies import get_current_user
from .dto import InviteResponse, MeResponse
from .errors import forbidden, invalid_input, invite_already_used, invite_expired

_log = logging.getLogger(__name__)

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
oauth.register(
    name="microsoft",
    client_id=os.environ.get("MS_OAUTH_CLIENT_ID", ""),
    client_secret=os.environ.get("MS_OAUTH_CLIENT_SECRET", ""),
    server_metadata_url="https://login.microsoftonline.com/common/v2.0/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

_GOOGLE_REDIRECT_URL = os.environ.get("OAUTH_REDIRECT_URL", "http://localhost:8000/api/auth/callback")
_MS_REDIRECT_URL = os.environ.get("MS_OAUTH_REDIRECT_URL", "http://localhost:8000/api/auth/callback/microsoft")
_FRONTEND_BASE = os.environ.get("FRONTEND_BASE_URL", "http://localhost:3000")


# ── Rate limiter ─────────────────────────────────────────────────────────────

class _RateLimiter:
    """Simple in-memory rate limiter with TTL cleanup."""

    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._attempts: dict[str, list[float]] = collections.defaultdict(list)

    def check(self, key: str) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        now = time.time()
        cutoff = now - self.window
        # Clean old entries
        self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
        if len(self._attempts[key]) >= self.max_attempts:
            return False
        self._attempts[key].append(now)
        return True

    def record_failure(self, key: str) -> None:
        """Record a failed attempt (already counted by check)."""
        pass  # check() already records the attempt


_login_limiter = _RateLimiter(max_attempts=5, window_seconds=900)  # 5 per 15min
_register_limiter = _RateLimiter(max_attempts=3, window_seconds=3600)  # 3 per hour
_forgot_limiter = _RateLimiter(max_attempts=3, window_seconds=3600)  # 3 per hour


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


def _cookie_secure() -> bool:
    explicit = os.getenv("COOKIE_SECURE")
    if explicit is not None:
        return explicit.lower() == "true"
    return _GOOGLE_REDIRECT_URL.startswith("https://")


def _cookie_samesite() -> str:
    explicit = os.getenv("COOKIE_SAMESITE")
    if explicit:
        return explicit.lower()
    return "lax"


def _set_session_cookie(response, signed_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=signed_token,
        httponly=True,
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
        max_age=SESSION_TTL_DAYS * 86_400,
        path="/",
    )


def _cookie_redirect(url: str, signed_token: str):
    """Return an HTML page that sets the session cookie then redirects."""
    from starlette.responses import HTMLResponse

    html = (
        "<!DOCTYPE html><html><head>"
        f'<meta http-equiv="refresh" content="0;url={url}">'
        "</head><body></body></html>"
    )
    resp = HTMLResponse(content=html, status_code=200)
    _set_session_cookie(resp, signed_token)
    return resp


def _handle_oauth_login(
    *,
    provider: str,
    email: str,
    sub: str,
    display_name: Optional[str],
    picture: Optional[str],
    invite_token: Optional[str],
):
    """Shared handler for Google and Microsoft OAuth callbacks.

    1. Existing credential → session for existing user
    2. Email exists (different provider) → link new credential → session
    3. Invite-based signup → create user + credential → session
    4. Admin signup → create user + credential → session
    5. No valid path → 403
    """
    # ── Case 1: existing credential for this provider + sub ──
    cred = get_credential(provider, sub)
    if cred:
        user = get_user_by_email(email) or _get_user_by_id_safe(cred.user_id)
        if user:
            update_last_login(user.id)
            if picture:
                update_profile_photo_url(user.id, picture)
            _sync_airtable_user(user)
            signed = create_session(user.id)
            return _cookie_redirect(_FRONTEND_BASE + landing_url_for(user.role), signed)

    # ── Case 2: account linking — email exists under a different provider ──
    existing = get_user_by_email(email)
    if existing:
        # Link new credential to existing account
        existing_cred = get_credential_by_user(existing.id, provider)
        if not existing_cred:
            create_credential(
                user_id=existing.id,
                provider=provider,
                provider_sub=sub,
                email_verified=True,
            )
        update_last_login(existing.id)
        if picture:
            update_profile_photo_url(existing.id, picture)
        _sync_airtable_user(existing)
        signed = create_session(existing.id)
        return _cookie_redirect(_FRONTEND_BASE + landing_url_for(existing.role), signed)

    # ── Case 3: invite-based signup ──
    if invite_token:
        token_data = validate_invite_token(invite_token)
        if token_data is None:
            from ..auth.sqlite_db import get_conn as _gc
            with _gc() as c:
                with c.cursor() as _cur:
                    _cur.execute("SELECT * FROM invite_tokens WHERE token = %s", (invite_token,))
                    row = _cur.fetchone()
            if row and row["used_by"]:
                return invite_already_used()
            return invite_expired()

        new_user = create_user(
            email=email,
            display_name=display_name,
            role=token_data["role"],
            oauth_provider=provider,
            oauth_sub=sub,
            coach_id=token_data["coach_id"],
            profile_photo_url=picture,
        )
        create_credential(
            user_id=new_user.id,
            provider=provider,
            provider_sub=sub,
            email_verified=True,
        )
        consume_invite_token(invite_token, new_user.id)
        _sync_airtable_user(new_user)
        signed = create_session(new_user.id)
        return _cookie_redirect(_FRONTEND_BASE + landing_url_for(new_user.role), signed)

    # ── Case 4: admin signup ──
    if email in ADMIN_EMAILS:
        new_user = create_user(
            email=email,
            display_name=display_name,
            role="coach",
            oauth_provider=provider,
            oauth_sub=sub,
            profile_photo_url=picture,
        )
        create_credential(
            user_id=new_user.id,
            provider=provider,
            provider_sub=sub,
            email_verified=True,
        )
        _sync_airtable_user(new_user)
        signed = create_session(new_user.id)
        return _cookie_redirect(_FRONTEND_BASE + landing_url_for("admin"), signed)

    # ── No valid path ──
    return forbidden("Access denied. Please use an invite link to register.")


def _get_user_by_id_safe(user_id: str) -> Optional[UserAuth]:
    from .auth import get_user_by_id
    return get_user_by_id(user_id)


def _parse_invite_from_state(request: Request) -> Optional[str]:
    """Extract invite_token from OAuth state parameter."""
    raw_state = request.query_params.get("state", "")
    if raw_state:
        try:
            return json.loads(raw_state).get("invite_token")
        except (json.JSONDecodeError, AttributeError):
            pass
    return None


# ── OAuth Routes ─────────────────────────────────────────────────────────────

@router.get("/api/auth/login")
async def login_google(request: Request, invite_token: Optional[str] = None):
    """Redirect to Google OAuth."""
    state_data = json.dumps({"invite_token": invite_token}) if invite_token else None
    return await oauth.google.authorize_redirect(
        request, _GOOGLE_REDIRECT_URL, state=state_data, prompt="select_account"
    )


@router.get("/api/auth/login/microsoft")
async def login_microsoft(request: Request, invite_token: Optional[str] = None):
    """Redirect to Microsoft OAuth."""
    state_data = json.dumps({"invite_token": invite_token}) if invite_token else None
    return await oauth.microsoft.authorize_redirect(
        request, _MS_REDIRECT_URL, state=state_data, prompt="select_account"
    )


@router.get("/api/auth/callback")
async def callback_google(request: Request):
    """Handle Google OAuth callback."""
    token = await oauth.google.authorize_access_token(request)
    user_info = token.get("userinfo") or await oauth.google.userinfo(token=token)

    return _handle_oauth_login(
        provider="google",
        email=(user_info.get("email") or "").lower(),
        sub=user_info.get("sub", ""),
        display_name=user_info.get("name"),
        picture=user_info.get("picture"),
        invite_token=_parse_invite_from_state(request),
    )


@router.get("/api/auth/callback/microsoft")
async def callback_microsoft(request: Request):
    """Handle Microsoft OAuth callback."""
    token = await oauth.microsoft.authorize_access_token(request)
    user_info = token.get("userinfo", {})

    # Microsoft returns 'oid' or 'sub' as unique identifier
    sub = user_info.get("sub") or user_info.get("oid", "")
    email = (user_info.get("email") or user_info.get("preferred_username") or "").lower()
    display_name = user_info.get("name")
    # Microsoft doesn't provide profile photo in userinfo — leave as None
    picture = None

    return _handle_oauth_login(
        provider="microsoft",
        email=email,
        sub=sub,
        display_name=display_name,
        picture=picture,
        invite_token=_parse_invite_from_state(request),
    )


# ── Email/Password Routes ───────────────────────────────────────────────────

class RegisterBody(BaseModel):
    email: str
    password: str
    display_name: str | None = None
    invite_token: str | None = None


class LoginEmailBody(BaseModel):
    email: str
    password: str


class ForgotPasswordBody(BaseModel):
    email: str


class ResetPasswordBody(BaseModel):
    token: str
    new_password: str


class VerifyEmailBody(BaseModel):
    token: str


@router.post("/api/auth/register")
async def register_email(body: RegisterBody, request: Request):
    """Register a new user with email + password."""
    # Rate limit by IP
    client_ip = request.client.host if request.client else "unknown"
    if not _register_limiter.check(client_ip):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many registration attempts. Try again later."},
        )

    # Validate password strength
    pw_error = validate_password_strength(body.password)
    if pw_error:
        return invalid_input(pw_error)

    email = body.email.strip().lower()
    if not email or "@" not in email:
        return invalid_input("A valid email address is required.")

    # Check if email already exists
    existing = get_user_by_email(email)
    if existing:
        # Check if they already have an email credential
        existing_cred = get_credential_by_user(existing.id, "email")
        if existing_cred:
            return invalid_input("An account with this email already exists. Try signing in instead.")
        # Account exists via OAuth — allow adding password credential
        pw_hash = hash_password(body.password)
        create_credential(
            user_id=existing.id,
            provider="email",
            password_hash=pw_hash,
            email_verified=True,  # Already verified via OAuth
        )
        return JSONResponse({"status": "ok", "message": "Password added to your existing account. You can now sign in with email and password."})

    # New user — check invite or admin list
    role: str | None = None
    coach_id: str | None = None

    if body.invite_token:
        token_data = validate_invite_token(body.invite_token)
        if token_data is None:
            return invalid_input("Invalid or expired invite link.")
        role = token_data["role"]
        coach_id = token_data["coach_id"]
    elif email in ADMIN_EMAILS:
        role = "coach"
    else:
        return forbidden("Access denied. Please use an invite link to register.")

    pw_hash = hash_password(body.password)
    new_user = create_user(
        email=email,
        display_name=body.display_name,
        role=role,
        coach_id=coach_id,
    )
    create_credential(
        user_id=new_user.id,
        provider="email",
        password_hash=pw_hash,
        email_verified=False,
    )

    if body.invite_token:
        consume_invite_token(body.invite_token, new_user.id)

    # Send verification email
    token = generate_email_token(new_user.id, "verify_email", ttl_hours=24)
    from ..core.email_service import send_verification_email
    send_verification_email(email, token, _FRONTEND_BASE)

    _sync_airtable_user(new_user)

    return JSONResponse({
        "status": "ok",
        "message": "Account created. Please check your email to verify your address.",
    })


@router.post("/api/auth/login/email")
async def login_email(body: LoginEmailBody):
    """Sign in with email + password."""
    email = body.email.strip().lower()

    if not _login_limiter.check(email):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many login attempts. Try again in a few minutes."},
        )

    user = get_user_by_email(email)
    if not user:
        return invalid_input("Invalid email or password.")

    cred = get_credential_by_user(user.id, "email")
    if not cred or not cred.password_hash:
        return invalid_input("Invalid email or password.")

    if not verify_password(body.password, cred.password_hash):
        return invalid_input("Invalid email or password.")

    if not cred.email_verified:
        return invalid_input("Please verify your email address before signing in. Check your inbox for a verification link.")

    update_last_login(user.id)
    signed = create_session(user.id)

    resp = JSONResponse({
        "status": "ok",
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
    })
    _set_session_cookie(resp, signed)
    return resp


@router.post("/api/auth/verify-email")
async def verify_email_route(body: VerifyEmailBody):
    """Verify a user's email address using a token from the verification email."""
    token_data = validate_email_token(body.token, "verify_email")
    if not token_data:
        return invalid_input("Invalid or expired verification link.")

    user_id = token_data["user_id"]
    cred = get_credential_by_user(user_id, "email")
    if not cred:
        return invalid_input("No email credential found.")

    set_email_verified(cred.id)
    consume_email_token(body.token)

    return JSONResponse({"status": "ok", "message": "Email verified. You can now sign in."})


@router.post("/api/auth/forgot-password")
async def forgot_password(body: ForgotPasswordBody):
    """Send a password reset email. Always returns 200 to avoid leaking email existence."""
    email = body.email.strip().lower()

    if not _forgot_limiter.check(email):
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests. Try again later."},
        )

    user = get_user_by_email(email)
    if user:
        cred = get_credential_by_user(user.id, "email")
        if cred:
            token = generate_email_token(user.id, "password_reset", ttl_hours=1)
            from ..core.email_service import send_password_reset_email
            send_password_reset_email(email, token, _FRONTEND_BASE)

    # Always return the same response to avoid leaking whether the email exists
    return JSONResponse({
        "status": "ok",
        "message": "If an account with that email exists, we've sent a password reset link.",
    })


@router.post("/api/auth/reset-password")
async def reset_password(body: ResetPasswordBody):
    """Reset a user's password using a token from the reset email."""
    pw_error = validate_password_strength(body.new_password)
    if pw_error:
        return invalid_input(pw_error)

    token_data = validate_email_token(body.token, "password_reset")
    if not token_data:
        return invalid_input("Invalid or expired reset link.")

    user_id = token_data["user_id"]
    cred = get_credential_by_user(user_id, "email")
    if not cred:
        return invalid_input("No email credential found.")

    new_hash = hash_password(body.new_password)
    update_password_hash(cred.id, new_hash)
    consume_email_token(body.token)

    return JSONResponse({"status": "ok", "message": "Password reset successfully. You can now sign in."})


# ── Session Routes ───────────────────────────────────────────────────────────

@router.post("/api/auth/logout")
async def logout(
    sid: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
):
    if sid:
        delete_session(sid)
    resp = JSONResponse({"status": "logged_out"})
    resp.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=_cookie_secure(),
        samesite=_cookie_samesite(),
    )
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
        profile_photo_url=user.profile_photo_url,
        last_login=user.last_login,
    )


# ── Invite Routes ────────────────────────────────────────────────────────────

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
