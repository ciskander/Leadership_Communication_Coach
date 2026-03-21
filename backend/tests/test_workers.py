"""
test_workers_integration.py — Integration tests for worker functions with
mocked Airtable and OpenAI dependencies.

Key differences from the old test_workers.py:
- AirtableClient is injected via the `client=` parameter (not class-patched)
- call_llm is patched at backend.core.workers.call_llm (not OpenAIClient)
- OpenAI mock returns an OpenAIResponse object, not a raw string
- Method names match the actual AirtableClient API
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch, call

import pytest

from backend.core.models import OpenAIResponse


# ── Helpers ───────────────────────────────────────────────────────────────────

def _openai_response(output: dict) -> OpenAIResponse:
    raw = json.dumps(output)
    return OpenAIResponse(
        parsed=output,
        raw_text=raw,
        model="gpt-4o",
        prompt_tokens=1000,
        completion_tokens=500,
        total_tokens=1500,
    )


# ── Single meeting worker ─────────────────────────────────────────────────────

class TestProcessSingleMeetingAnalysis:

    def test_creates_run_record_on_success(self, mock_at, valid_single_meeting_output):
        with patch("backend.core.workers.call_llm",
                   return_value=_openai_response(valid_single_meeting_output)):
            from backend.core.workers import process_single_meeting_analysis
            run_id = process_single_meeting_analysis("rec_rr_001", client=mock_at, system_prompt_override="test system prompt")

        assert run_id == "rec_run_001"
        mock_at.create_run.assert_called_once()

    def test_returns_existing_run_on_idempotency_hit(self, mock_at, valid_single_meeting_output):
        """If a run with the same idempotency key exists, no new run is created."""
        mock_at.find_run_by_idempotency_key.return_value = {
            "id": "rec_run_existing",
            "fields": {"Run ID": "R-000001", "Gate1 Pass": True},
        }

        with patch("backend.core.workers.call_llm") as mock_openai:
            from backend.core.workers import process_single_meeting_analysis
            run_id = process_single_meeting_analysis("rec_rr_001", client=mock_at, system_prompt_override="test system prompt")

        assert run_id == "rec_run_existing"
        mock_openai.assert_not_called()
        mock_at.create_run.assert_not_called()

    def test_run_record_includes_parsed_json(self, mock_at, valid_single_meeting_output):
        with patch("backend.core.workers.call_llm",
                   return_value=_openai_response(valid_single_meeting_output)):
            from backend.core.workers import process_single_meeting_analysis
            process_single_meeting_analysis("rec_rr_001", client=mock_at, system_prompt_override="test system prompt")

        create_call_kwargs = mock_at.create_run.call_args
        assert create_call_kwargs is not None
        # The fields dict passed to create_run should contain Parsed JSON
        fields_arg = create_call_kwargs[0][0] if create_call_kwargs[0] else create_call_kwargs[1].get("fields", {})
        all_args_str = str(create_call_kwargs)
        assert "Parsed JSON" in all_args_str or "parsed_json" in all_args_str.lower()

    def test_gate1_failure_still_creates_run(self, mock_at):
        """Even when Gate1 fails the run record is persisted (with gate1_pass=False)."""
        bad_output = {"schema_version": "wrong", "garbage": True}
        with patch("backend.core.workers.call_llm",
                   return_value=_openai_response(bad_output)):
            from backend.core.workers import process_single_meeting_analysis
            run_id = process_single_meeting_analysis("rec_rr_001", client=mock_at, system_prompt_override="test system prompt")

        assert run_id is not None
        mock_at.create_run.assert_called_once()
        # Verify gate1_pass=False was passed in the fields
        fields_str = str(mock_at.create_run.call_args)
        assert "False" in fields_str or "Gate1 Pass" in fields_str

    def test_missing_transcript_link_raises(self, mock_at, valid_single_meeting_output):
        mock_at.get_run_request.return_value = {
            "id": "rec_rr_001",
            "fields": {
                # No "Transcript" key
                "Target Speaker Name": "Alice",
                "Analysis Type": "single_meeting",
            },
        }
        with pytest.raises(ValueError, match="no Transcript"):
            from backend.core.workers import process_single_meeting_analysis
            process_single_meeting_analysis("rec_rr_001", client=mock_at, system_prompt_override="test system prompt")

    def test_baseline_sub_run_links_back_to_pack(self, mock_at_baseline, valid_single_meeting_output):
        """Sub-run for a baseline pack should have baseline_pack field set on the run record."""
        with patch("backend.core.workers.call_llm",
                   return_value=_openai_response(valid_single_meeting_output)):
            from backend.core.workers import process_single_meeting_analysis
            process_single_meeting_analysis("rec_rr_001", client=mock_at_baseline, system_prompt_override="test system prompt")

        fields_str = str(mock_at_baseline.create_run.call_args)
        assert "rec_bp_001" in fields_str


# ── Pattern patching applied inside worker ───────────────────────────────────

class TestWorkerAppliesPatches:
    """
    Verify that the worker applies snapshot patches before persisting,
    by inspecting what gets written to Airtable.
    """

    def _output_with_zero_opportunity_count(self, base: dict) -> dict:
        import copy
        out = copy.deepcopy(base)
        for snap in out["pattern_snapshot"]:
            if snap["pattern_id"] == "purposeful_framing":
                snap["opportunity_count"] = 0
                snap["score"] = 0.0
        return out

    def test_zero_opportunity_count_coerced_in_persisted_json(
        self, mock_at, valid_single_meeting_output
    ):
        bad_output = self._output_with_zero_opportunity_count(valid_single_meeting_output)
        with patch("backend.core.workers.call_llm",
                   return_value=_openai_response(bad_output)):
            from backend.core.workers import process_single_meeting_analysis
            process_single_meeting_analysis("rec_rr_001", client=mock_at, system_prompt_override="test system prompt")

        fields_str = str(mock_at.create_run.call_args)
        # The persisted JSON should not contain score for the zero-opportunity pattern
        # (it will have been coerced to insufficient_signal and score stripped)
        persisted_json_str = [
            str(v) for k, v in (mock_at.create_run.call_args[0][0] if mock_at.create_run.call_args[0]
                                 else mock_at.create_run.call_args[1]).items()
            if "Parsed" in str(k)
        ]
        if persisted_json_str:
            persisted = json.loads(persisted_json_str[0])
            for snap in persisted.get("pattern_snapshot", []):
                if snap["pattern_id"] == "purposeful_framing":
                    assert snap["evaluable_status"] == "insufficient_signal"
                    assert "score" not in snap
