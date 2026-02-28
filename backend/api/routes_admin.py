"""
api/routes_admin.py — Admin-only endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth.models import UserAuth
from .auth import list_all_users, promote_to_coach
from .dependencies import get_current_user
from .dto import AdminUserListItem
from .errors import error_response

router = APIRouter()


def _require_admin(user: UserAuth) -> UserAuth:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


@router.get("/api/admin/users", response_model=list[AdminUserListItem])
async def admin_list_users(user: UserAuth = Depends(get_current_user)):
    _require_admin(user)
    users = list_all_users()
    return [
        AdminUserListItem(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            role=u.role,
            coach_id=u.coach_id,
            created_at=u.created_at,
            last_login=u.last_login,
        )
        for u in users
    ]


@router.post("/api/admin/users/{user_id}/promote")
async def admin_promote_user(
    user_id: str,
    user: UserAuth = Depends(get_current_user),
):
    _require_admin(user)
    from .auth import get_user_by_id
    target = get_user_by_id(user_id)
    if not target:
        return error_response("NOT_FOUND", f"User {user_id} not found.", 404)
    promote_to_coach(user_id)
    return {"user_id": user_id, "new_role": "coach"}
