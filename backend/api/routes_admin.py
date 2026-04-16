"""
api/routes_admin.py — Admin-only endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..auth.models import UserAuth
from ..core.airtable_client import (
    AirtableClient,
    F_CFG_REDACTION_ENABLED,
    F_CFG_REDACTION_AGGRESSIVENESS,
    F_CFG_REDACTION_REVERSIBLE,
    F_CFG_REDACTION_ORG_NAMES,
    F_CFG_SHARE_ORIGINAL,
)
from .auth import list_all_users, promote_to_coach
from .dependencies import get_current_user
from .dto import AdminUserListItem, RedactionSettingsResponse, RedactionSettingsUpdate
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


# ── Redaction Settings ────────────────────────────────────────────────────────

_REDACTION_DEFAULTS = {
    "redaction_enabled": True,
    "aggressiveness": "standard",
    "reversible": True,
    "redact_org_names": False,
    "share_original_enabled": False,
}

_FIELD_MAP = {
    "redaction_enabled": F_CFG_REDACTION_ENABLED,
    "aggressiveness": F_CFG_REDACTION_AGGRESSIVENESS,
    "reversible": F_CFG_REDACTION_REVERSIBLE,
    "redact_org_names": F_CFG_REDACTION_ORG_NAMES,
    "share_original_enabled": F_CFG_SHARE_ORIGINAL,
}


def _extract_redaction_settings(cfg_fields: dict) -> dict:
    """Extract redaction settings from Airtable config fields with defaults."""
    return {
        "redaction_enabled": cfg_fields.get(F_CFG_REDACTION_ENABLED, _REDACTION_DEFAULTS["redaction_enabled"]),
        "aggressiveness": cfg_fields.get(F_CFG_REDACTION_AGGRESSIVENESS, _REDACTION_DEFAULTS["aggressiveness"]),
        "reversible": cfg_fields.get(F_CFG_REDACTION_REVERSIBLE, _REDACTION_DEFAULTS["reversible"]),
        "redact_org_names": cfg_fields.get(F_CFG_REDACTION_ORG_NAMES, _REDACTION_DEFAULTS["redact_org_names"]),
        "share_original_enabled": cfg_fields.get(F_CFG_SHARE_ORIGINAL, _REDACTION_DEFAULTS["share_original_enabled"]),
    }


@router.get("/api/admin/settings/redaction", response_model=RedactionSettingsResponse)
async def get_redaction_settings(user: UserAuth = Depends(get_current_user)):
    """Get current redaction settings from the active Airtable config."""
    _require_admin(user)
    client = AirtableClient()
    active_cfg = client.get_active_config()
    if not active_cfg:
        return RedactionSettingsResponse(**_REDACTION_DEFAULTS)
    cfg_fields = active_cfg.get("fields", {})
    return RedactionSettingsResponse(**_extract_redaction_settings(cfg_fields))


@router.put("/api/admin/settings/redaction", response_model=RedactionSettingsResponse)
async def update_redaction_settings(
    body: RedactionSettingsUpdate,
    user: UserAuth = Depends(get_current_user),
):
    """Update redaction settings on the active Airtable config record."""
    _require_admin(user)
    client = AirtableClient()
    active_cfg = client.get_active_config()
    if not active_cfg:
        raise HTTPException(status_code=404, detail="No active config record found in Airtable.")

    # Build update payload from non-None fields
    updates = body.model_dump(exclude_none=True)
    if "aggressiveness" in updates and updates["aggressiveness"] not in ("conservative", "standard", "permissive"):
        raise HTTPException(status_code=422, detail="aggressiveness must be one of: conservative, standard, permissive")

    airtable_updates = {}
    for key, value in updates.items():
        if key in _FIELD_MAP:
            airtable_updates[_FIELD_MAP[key]] = value

    if airtable_updates:
        client.update_record("config", active_cfg["id"], airtable_updates)

    # Re-read to return current state
    updated_cfg = client.get_active_config()
    cfg_fields = updated_cfg.get("fields", {}) if updated_cfg else {}
    return RedactionSettingsResponse(**_extract_redaction_settings(cfg_fields))
