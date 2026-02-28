"""
test_idempotency.py — Tests for duplicate detection / idempotency.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.core.idempotency import make_run_idempotency_key


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

def test_idempotency_key_is_deterministic():
    key1 = make_run_idempotency_key(
        transcript_id="rec_tr_001",
        analysis_type="single_meeting",
        coachee_id="rec_user_001",
        target_speaker_label="Alice",
        target_role="chair",
        config_version="mvp.v0.2.1",
    )
    key2 = make_run_idempotency_key(
        transcript_id="rec_tr_001",
        analysis_type="single_meeting",
        coachee_id="rec_user_001",
        target_speaker_label="Alice",
        target_role="chair",
        config_version="mvp.v0.2.1",
    )
    assert key1 == key2


def test_idempotency_key_changes_with_different_transcript():
    key1 = make_run_idempotency_key(
        transcript_id="rec_tr_001",
        analysis_type="single_meeting",
        coachee_id="rec_user_001",
        target_speaker_label="Alice",
        target_role="chair",
        config_version="mvp.v0.2.1",
    )
    key2 = make_run_idempotency_key(
        transcript_id="rec_tr_002",  # different transcript
        analysis_type="single_meeting",
        coachee_id="rec_user_001",
        target_speaker_label="Alice",
        target_role="chair",
        config_version="mvp.v0.2.1",
    )
    assert key1 != key2


def test_idempotency_key_changes_with_different_speaker_label():
    key1 = make_run_idempotency_key(
        transcript_id="rec_tr_001",
        analysis_type="single_meeting",
        coachee_id="rec_user_001",
        target_speaker_label="Alice",
        target_role="chair",
        config_version="mvp.v0.2.1",
    )
    key2 = make_run_idempotency_key(
        transcript_id="rec_tr_001",
        analysis_type="single_meeting",
        coachee_id="rec_user_001",
        target_speaker_label="Bob",  # different speaker
        target_role="chair",
        config_version="mvp.v0.2.1",
    )
    assert key1 != key2


def test_idempotency_key_case_insensitive_for_speaker_label():
    key1 = make_run_idempotency_key(
        transcript_id="rec_tr_001",
        analysis_type="single_meeting",
        coachee_id="rec_user_001",
        target_speaker_label="alice",
        target_role="chair",
        config_version="mvp.v0.2.1",
    )
    key2 = make_run_idempotency_key(
        transcript_id="rec_tr_001",
        analysis_type="single_meeting",
        coachee_id="rec_user_001",
        target_speaker_label="ALICE",  # different casing
        target_role="chair",
        config_version="mvp.v0.2.1",
    )
    # Per the implementation, speaker labels are lowercased before hashing
    assert key1 == key2


def test_idempotency_key_is_hex_string():
    key = make_run_idempotency_key(
        transcript_id="x",
        analysis_type="single_meeting",
        coachee_id="y",
        target_speaker_label="z",
        target_role="chair",
        config_version="mvp.v0.2.1",
    )
    # SHA-256 hex is 64 chars
    assert len(key) == 64
    assert all(c in "0123456789abcdef" for c in key)


# ---------------------------------------------------------------------------
# Worker-level idempotency (second call is no-op)
# ---------------------------------------------------------------------------

def test_worker_skips_run_if_idempotency_key_exists(
    mock_airtable, mock_openai, valid_single_meeting_output
):
    """If an existing run with the same idempotency key exists, no new run is created."""
    existing_run = {"id": "rec_run_existing", "fields": {"Run ID": "R-000001"}}
    mock_airtable.check_run_idempotency.return_value = existing_run  # key already exists
    mock_airtable.get_run_request.return_value = {
        "id": "rec_rr_001",
        "fields": {
            "Request ID": "rr-001",
            "Transcript Record ID": "rec_tr_001",
            "Target Speaker Name": "Alice",
            "Target Speaker Label": "Alice",
            "Target Role": "chair",
            "Analysis Type": "single_meeting",
            "Status": "queued",
            "Coachee User Record ID": "rec_user_001",
        },
    }
    mock_airtable.get_transcript.return_value = {
        "id": "rec_tr_001",
        "fields": {
            "Raw Text": "Alice: Hello.\nBob: Hi.",
            "Meeting Type": "exec_staff",
            "Meeting Date": "2026-02-12",
            "Meeting ID": "M-000001",
            "Speaker Labels": json.dumps(["Alice", "Bob"]),
        },
    }

    with patch("backend.core.workers.AirtableClient", return_value=mock_airtable), \
         patch("backend.core.workers.OpenAIClient", return_value=mock_openai):
        from backend.core.workers import process_single_meeting_analysis
        run_id = process_single_meeting_analysis("rec_rr_001")

    # create_run should NOT have been called (second call is no-op)
    mock_airtable.create_run.assert_not_called()
    # Should return the existing run ID
    assert run_id == "rec_run_existing"
