"""
test_api_auth.py — Tests for role guards and session management.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App factory fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    from backend.api.app import create_app
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _make_user(role: str = "coachee"):
    from backend.auth.models import UserAuth
    return UserAuth(
        id="user-001",
        email="test@example.com",
        display_name="Test User",
        role=role,
        coach_id=None,
        airtable_user_record_id="rec_user_001",
        oauth_provider="google",
        oauth_sub="google-sub-001",
    )


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

def test_me_unauthenticated_returns_401(client):
    resp = client.get("/api/me")
    assert resp.status_code == 401


def test_client_summary_unauthenticated_returns_401(client):
    resp = client.get("/api/client/summary")
    assert resp.status_code == 401


def test_coach_coachees_unauthenticated_returns_401(client):
    resp = client.get("/api/coach/coachees")
    assert resp.status_code == 401


def test_admin_users_unauthenticated_returns_401(client):
    resp = client.get("/api/admin/users")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Role-based access control
# ---------------------------------------------------------------------------

def test_coachee_cannot_access_admin_routes(client, app):
    coachee = _make_user(role="coachee")
    from backend.api.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: coachee
    try:
        resp = client.get("/api/admin/users")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code in (403, 401)


def test_coachee_cannot_access_coach_routes(client, app):
    coachee = _make_user(role="coachee")
    from backend.api.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: coachee
    try:
        resp = client.get("/api/coach/coachees")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code in (403, 401)


def test_coach_can_access_coach_routes(client, app):
    coach = _make_user(role="coach")
    from backend.api.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: coach
    try:
        with patch("backend.api.routes_coach.list_coachees_for_coach", return_value=[]):
            resp = client.get("/api/coach/coachees")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200


def test_coach_cannot_access_admin_routes(client, app):
    coach = _make_user(role="coach")
    from backend.api.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: coach
    try:
        resp = client.get("/api/admin/users")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code in (403, 401)


def test_admin_can_access_admin_routes(client, app):
    admin = _make_user(role="admin")
    from backend.api.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        with patch("backend.api.routes_admin.list_all_users", return_value=[]):
            resp = client.get("/api/admin/users")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Authenticated /api/me
# ---------------------------------------------------------------------------

def test_me_returns_user_for_authenticated_request(client, app):
    user = _make_user(role="coachee")
    from backend.api.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        resp = client.get("/api/me")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "coachee"
    assert data["email"] == "test@example.com"


# ---------------------------------------------------------------------------
# Session / token edge cases
# ---------------------------------------------------------------------------

def test_invalid_bearer_token_returns_401(client):
    resp = client.get(
        "/api/me",
        headers={"Authorization": "Bearer invalid-token-here"},
    )
    assert resp.status_code == 401


def test_coachee_can_access_own_summary(client, app):
    user = _make_user(role="coachee")
    from backend.api.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch("backend.core.airtable_client.AirtableClient") as MockAT:
            at = MagicMock()
            MockAT.return_value = at
            at.get_user_by_id.return_value = {
                "id": "rec_user_001",
                "fields": {"Role": "coachee"},
            }
            at.get_active_experiment.return_value = None
            at.get_baseline_pack_for_user.return_value = None
            at.list_runs_for_user.return_value = []
            resp = client.get("/api/client/summary")
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Baseline pack route guards
# ---------------------------------------------------------------------------

def test_coachee_can_create_baseline_pack(client, app):
    user = _make_user(role="coachee")
    from backend.api.dependencies import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        with patch("backend.api.routes_coachee.AirtableClient") as MockAT:
            at = MagicMock()
            MockAT.return_value = at
            at.create_record.return_value = {
                "id": "rec_bp_001",
                "fields": {"Baseline Pack ID": "BP-000001"},
            }
            resp = client.post(
                "/api/baseline_packs",
                json={
                    "transcript_ids": ["rec_tr_001", "rec_tr_002", "rec_tr_003"],
                    "target_speaker_name": "Alice",
                    "target_speaker_label": "Alice",
                    "target_role": "chair",
                },
            )
    finally:
        app.dependency_overrides.clear()
    assert resp.status_code in (200, 201)
