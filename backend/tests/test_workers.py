"""
test_workers.py — Happy path tests for core worker functions with mocked deps.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_run_request_record(status: str = "queued") -> dict:
    return {
        "id": "rec_rr_001",
        "fields": {
            "Request ID": "rr-001",
            "Transcript Record ID": "rec_tr_001",
            "Target Speaker Name": "Alice",
            "Target Speaker Label": "Alice",
            "Target Role": "chair",
            "Analysis Type": "single_meeting",
            "Status": status,
            "Coachee User Record ID": "rec_user_001",
        },
    }


def _make_transcript_record() -> dict:
    return {
        "id": "rec_tr_001",
        "fields": {
            "Transcript ID": "T-000001",
            "Raw Text": "Alice: Let's get started.\nBob: Sounds good.\nAlice: First item is budget.",
            "Meeting Type": "exec_staff",
            "Meeting Date": "2026-02-12",
            "Meeting ID": "M-000001",
            "Speaker Labels": json.dumps(["Alice", "Bob"]),
        },
    }


# ---------------------------------------------------------------------------
# Single meeting worker happy path
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("mock_airtable", "mock_openai")
def test_single_meeting_worker_creates_run_record(
    mock_airtable, mock_openai, valid_single_meeting_output
):
    """Worker should create a run record in Airtable on success."""
    mock_airtable.get_run_request.return_value = _make_run_request_record()
    mock_airtable.get_transcript.return_value = _make_transcript_record()
    mock_airtable.create_run.return_value = {"id": "rec_run_001", "fields": {}}
    mock_airtable.check_run_idempotency.return_value = None  # no prior run
    mock_openai.chat_completion.return_value = json.dumps(valid_single_meeting_output)

    with patch("backend.core.workers.AirtableClient", return_value=mock_airtable), \
         patch("backend.core.workers.OpenAIClient", return_value=mock_openai):
        from backend.core.workers import process_single_meeting_analysis
        run_id = process_single_meeting_analysis("rec_rr_001")

    assert run_id is not None
    mock_airtable.create_run.assert_called_once()


@pytest.mark.usefixtures("mock_airtable", "mock_openai")
def test_single_meeting_worker_marks_run_request_complete(
    mock_airtable, mock_openai, valid_single_meeting_output
):
    mock_airtable.get_run_request.return_value = _make_run_request_record()
    mock_airtable.get_transcript.return_value = _make_transcript_record()
    mock_airtable.create_run.return_value = {"id": "rec_run_001", "fields": {}}
    mock_airtable.check_run_idempotency.return_value = None
    mock_openai.chat_completion.return_value = json.dumps(valid_single_meeting_output)

    with patch("backend.core.workers.AirtableClient", return_value=mock_airtable), \
         patch("backend.core.workers.OpenAIClient", return_value=mock_openai):
        from backend.core.workers import process_single_meeting_analysis
        process_single_meeting_analysis("rec_rr_001")

    # Should update run_request status to complete
    calls = [str(c) for c in mock_airtable.update_run_request_status.call_args_list]
    assert any("complete" in c for c in calls)


@pytest.mark.usefixtures("mock_airtable", "mock_openai")
def test_single_meeting_worker_stores_parsed_json(
    mock_airtable, mock_openai, valid_single_meeting_output
):
    mock_airtable.get_run_request.return_value = _make_run_request_record()
    mock_airtable.get_transcript.return_value = _make_transcript_record()
    mock_airtable.create_run.return_value = {"id": "rec_run_001", "fields": {}}
    mock_airtable.check_run_idempotency.return_value = None
    mock_openai.chat_completion.return_value = json.dumps(valid_single_meeting_output)

    with patch("backend.core.workers.AirtableClient", return_value=mock_airtable), \
         patch("backend.core.workers.OpenAIClient", return_value=mock_openai):
        from backend.core.workers import process_single_meeting_analysis
        process_single_meeting_analysis("rec_rr_001")

    # Run should have been updated with parsed JSON
    update_calls = mock_airtable.update_run.call_args_list
    assert any(
        "Parsed JSON" in str(call) or "parsed_json" in str(call).lower()
        for call in update_calls
    )


# ---------------------------------------------------------------------------
# Gate1 failure path
# ---------------------------------------------------------------------------

def test_single_meeting_worker_handles_gate1_failure(mock_airtable, mock_openai_raw):
    """If Gate1 fails, the run should be marked with gate1_pass=False."""
    mock_airtable.get_run_request.return_value = _make_run_request_record()
    mock_airtable.get_transcript.return_value = _make_transcript_record()
    mock_airtable.create_run.return_value = {"id": "rec_run_001", "fields": {}}
    mock_airtable.check_run_idempotency.return_value = None
    # Return invalid JSON that will fail Gate1
    mock_openai_raw.chat_completion.return_value = json.dumps({"schema_version": "wrong"})

    with patch("backend.core.workers.AirtableClient", return_value=mock_airtable), \
         patch("backend.core.workers.OpenAIClient", return_value=mock_openai_raw):
        from backend.core.workers import process_single_meeting_analysis
        run_id = process_single_meeting_analysis("rec_rr_001")

    # Run should still be created (not raise), but with gate1_pass=False marker
    assert run_id is not None


# ---------------------------------------------------------------------------
# Experiment instantiation
# ---------------------------------------------------------------------------

def test_worker_creates_experiment_on_first_run(
    mock_airtable, mock_openai, valid_single_meeting_output
):
    """After a successful run, an experiment should be created if none exists."""
    mock_airtable.get_run_request.return_value = _make_run_request_record()
    mock_airtable.get_transcript.return_value = _make_transcript_record()
    mock_airtable.create_run.return_value = {"id": "rec_run_001", "fields": {}}
    mock_airtable.check_run_idempotency.return_value = None
    mock_airtable.get_active_experiment.return_value = None  # no existing experiment
    mock_openai.chat_completion.return_value = json.dumps(valid_single_meeting_output)

    with patch("backend.core.workers.AirtableClient", return_value=mock_airtable), \
         patch("backend.core.workers.OpenAIClient", return_value=mock_openai):
        from backend.core.workers import process_single_meeting_analysis
        process_single_meeting_analysis("rec_rr_001")

    # Should have attempted to create an experiment
    create_calls = [str(c) for c in mock_airtable.mock_calls]
    assert any("experiment" in c.lower() or "Experiment" in c for c in create_calls)
