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
    with patch("backend.api.dependencies.get_current_user", return_value=coachee):
        resp = client.get("/api/admin/users")
    assert resp.status_code in (403, 401)


def test_coachee_cannot_access_coach_routes(client, app):
    coachee = _make_user(role="coachee")
    with patch("backend.api.dependencies.get_current_user", return_value=coachee):
        resp = client.get("/api/coach/coachees")
    assert resp.status_code in (403, 401)


def test_coach_can_access_coach_routes(client):
    coach = _make_user(role="coach")
    with patch("backend.api.dependencies.get_current_user", return_value=coach), \
         patch("backend.core.airtable_client.AirtableClient") as MockAT:
        MockAT.return_value.list_coachees.return_value = []
        resp = client.get("/api/coach/coachees")
    assert resp.status_code == 200


def test_coach_cannot_access_admin_routes(client):
    coach = _make_user(role="coach")
    with patch("backend.api.dependencies.get_current_user", return_value=coach):
        resp = client.get("/api/admin/users")
    assert resp.status_code in (403, 401)


def test_admin_can_access_admin_routes(client):
    admin = _make_user(role="admin")
    with patch("backend.api.dependencies.get_current_user", return_value=admin), \
         patch("backend.core.airtable_client.AirtableClient") as MockAT:
        MockAT.return_value.list_all_users.return_value = []
        resp = client.get("/api/admin/users")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Authenticated /api/me
# ---------------------------------------------------------------------------

def test_me_returns_user_for_authenticated_request(client):
    user = _make_user(role="coachee")
    with patch("backend.api.dependencies.get_current_user", return_value=user):
        resp = client.get("/api/me")
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


def test_coachee_can_access_own_summary(client):
    user = _make_user(role="coachee")
    with patch("backend.api.dependencies.get_current_user", return_value=user), \
         patch("backend.core.airtable_client.AirtableClient") as MockAT:
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
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Baseline pack route guards
# ---------------------------------------------------------------------------

def test_coachee_can_create_baseline_pack(client):
    user = _make_user(role="coachee")
    with patch("backend.api.dependencies.get_current_user", return_value=user), \
         patch("backend.core.airtable_client.AirtableClient") as MockAT, \
         patch("backend.queue.tasks.enqueue_single_meeting"):
        at = MagicMock()
        MockAT.return_value = at
        at.create_baseline_pack.return_value = {
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
    assert resp.status_code in (200, 201)
