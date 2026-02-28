"""
api/dependencies.py — FastAPI dependency injection: current user, role guards.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Cookie, Depends, HTTPException, status

from .auth import SESSION_COOKIE_NAME, resolve_session
from ..auth.models import UserAuth


def get_current_user(
    sid: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> UserAuth:
    if not sid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = resolve_session(sid)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired or invalid")
    return user


def require_role(*roles: str):
    """Return a dependency that enforces one of the given roles."""
    def _check(user: UserAuth = Depends(get_current_user)) -> UserAuth:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user.role}' is not permitted. Required: {roles}",
            )
        return user
    return _check


# Pre-built shortcuts
require_admin = require_role("admin")
require_coach = require_role("coach", "admin")
require_coachee = require_role("coachee")
require_any = require_role("admin", "coach", "coachee")
