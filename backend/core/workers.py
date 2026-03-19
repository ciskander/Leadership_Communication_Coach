"""
workers.py — Core job processing functions (no queue runner).

Each function is self-contained and idempotent. The queue runner (Prompt 2)
calls these functions.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from .airtable_client import (
    AirtableClient,
    F_BP_LAST_RUN,
    F_BP_MEETING_TYPE_CONSISTENCY,
    F_BP_ROLE_CONSISTENCY,
    F_BP_STATUS,
    F_BPI_MEETING_SUMMARY,
    F_BPI_RUN,
    F_BPI_STATUS,
    F_EE_ATTEMPT_COUNT,
    F_EE_ATTEMPT_ENUM,
    F_EE_DETECTION_MODEL,
    F_EE_EVIDENCE_SPAN_IDS,
    F_EE_EXPERIMENT,
    F_EE_IDEMPOTENCY_KEY,
    F_EE_MEETING_DATE,
    F_EE_RUN,
    F_EE_TRANSCRIPT,
    F_EE_USER,
    F_EXP_BASELINE_PACK,
    F_EXP_CREATED_FROM_RUN_ID,
    F_EXP_EXPERIMENT_ID,
    F_EXP_INSTRUCTIONS,
    F_EXP_PATTERN_ID,
    F_EXP_PROPOSED_BY_RUN,
    F_EXP_STATUS,
    F_EXP_SUCCESS_CRITERIA,
    F_EXP_SUCCESS_MARKER,
    F_EXP_TITLE,
    F_EXP_USER,
    F_RR_STATUS,
    F_RUN_ANALYSIS_TYPE,
    F_RUN_ATTEMPT_EVENT_CREATED,
    F_RUN_ATTEMPT_MODEL,
    F_RUN_BASELINE_PACK,
    F_RUN_BUSINESS_OK,
    F_RUN_COACHEE_ID,
    F_RUN_EVALUATED_COUNT,
    F_RUN_EVIDENCE_SPAN_COUNT,
    F_RUN_EXPERIMENT_ID_OUT,
    F_RUN_EXPERIMENT_INSTANTIATED,
    F_RUN_EXPERIMENT_STATUS_MODEL,
    F_RUN_FOCUS_PATTERN,
    F_RUN_GATE1_PASS,
    F_RUN_IDEMPOTENCY_KEY,
    F_RUN_MICRO_EXP_PATTERN,
    F_RUN_MODEL_NAME,
    F_RUN_PARSE_OK,
    F_RUN_PARSED_JSON,
    F_RUN_RAW_OUTPUT,
    F_RUN_REQUEST_PAYLOAD,
    F_RUN_RUN_ID,
    F_RUN_RUN_REQUESTS,
    F_RUN_SCHEMA_OK,
    F_RUN_SCHEMA_VERSION_OUT,
    F_RUN_STRENGTHS_PATTERNS,
    F_RUN_TARGET_SPEAKER_LABEL,
    F_RUN_TARGET_SPEAKER_NAME,
    F_RUN_TARGET_SPEAKER_ROLE,
    F_RUN_TRANSCRIPT,
    F_USER_ACTIVE_EXPERIMENT,
    F_EXP_STARTED_AT,
    F_EXP_ENDED_AT,
    F_EXP_ATTEMPT_COUNT,
    F_EXP_LAST_ATTEMPT_MODEL,
    F_EXP_LAST_ATTEMPT_DATE,
    F_RUN_ACTIVE_EXPERIMENT,
)
from .config import CONFIG_VERSION
from .gate1_validator import validate as gate1_validate
from .idempotency import (
    check_experiment_event_exists,
    check_experiment_exists,
    check_run_exists,
    make_experiment_event_key,
    make_run_idempotency_key,
)
from .models import MemoryBlock, ValidationIssue, OpenAIResponse
from .llm_client import call_llm
from .openai_client import load_baseline_system_prompt, load_next_experiment_system_prompt, load_system_prompt
from .prompt_builder import build_baseline_pack_prompt, build_memory_block, build_single_meeting_prompt
from .quote_cleanup import cleanup_parsed_json
from .transcript_parser import parse_transcript

# Feature flag: mirrors QUOTE_CLEANUP_ENABLED from quote_helpers.py
import os as _os
_CLEANUP_ENABLED = _os.getenv("QUOTE_CLEANUP_ENABLED", "0") == "1"

_VALID_MEETING_TYPES = {
    'exec_staff', 'board', 'all_hands', 'cross_functional', 'project_review',
    'sprint_planning', 'sprint_retrospective', 'stand_up', 'incident_review',
    'client_call', 'one_on_one', 'other',
}

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_fields(record: dict) -> dict:
    return record.get("fields", {})


def _safe_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _get_str(fields: dict, key: str) -> Optional[str]:
    val = fields.get(key)
    if isinstance(val, list) and val:
        return str(val[0])
    return str(val) if val is not None else None


def _get_link_ids(fields: dict, key: str) -> list[str]:
    val = fields.get(key, [])
    return val if isinstance(val, list) else []


def _extract_coaching_from_run(parsed_json: dict) -> dict:
    """Extract key coaching fields from a run's parsed JSON output."""
    coaching = parsed_json.get("coaching_output", {})
    focus = coaching.get("focus", [{}])[0] if coaching.get("focus") else {}
    micro = coaching.get("micro_experiment", [{}])[0] if coaching.get("micro_experiment") else {}
    strengths = coaching.get("strengths", [])
    return {
        "focus_pattern": focus.get("pattern_id"),
        "micro_experiment_pattern": micro.get("pattern_id"),
        "strengths_patterns": json.dumps([s.get("pattern_id") for s in strengths]),
        "experiment_id": micro.get("experiment_id"),
        "micro_experiment_title": micro.get("title"),
        "micro_experiment_instruction": micro.get("instruction"),
        "micro_experiment_success_marker": micro.get("success_marker"),
    }


def _build_slim_meeting_summary(run_fields: dict, parsed_json: dict) -> dict:
    """Build an enriched meeting summary dict for baseline pack prompt.

    Includes evidence_spans, per-pattern notes/coaching, and coaching messages
    so the baseline LLM can select and pass through real evidence rather than
    fabricating quotes.
    """
    ctx = parsed_json.get("context", {})
    eval_summary = parsed_json.get("evaluation_summary", {})
    pattern_snapshot = parsed_json.get("pattern_snapshot", [])
    coaching = parsed_json.get("coaching_output", {})
    evidence_spans = parsed_json.get("evidence_spans", [])

    meeting_id = ctx.get("meeting_id")

    # Enriched pattern snapshot: include notes, coaching_note, suggested_rewrite,
    # rewrite_for_span_id, evidence_span_ids, and success_evidence_span_ids
    enriched_snapshot = []
    for p in pattern_snapshot:
        item: dict = {
            "pattern_id": p.get("pattern_id"),
            "evaluable_status": p.get("evaluable_status"),
            "numerator": p.get("numerator"),
            "denominator": p.get("denominator"),
            "ratio": p.get("ratio"),
            "balance_assessment": p.get("balance_assessment"),
        }
        # Include coaching detail when present
        for key in ("notes", "coaching_note", "suggested_rewrite",
                     "rewrite_for_span_id", "evidence_span_ids",
                     "success_evidence_span_ids"):
            val = p.get(key)
            if val is not None:
                item[key] = val
        enriched_snapshot.append(item)

    # Enriched coaching output: include messages for strengths and focus
    strengths = coaching.get("strengths") or []
    focus = coaching.get("focus") or []
    micro = (coaching.get("micro_experiment") or [{}])[0]
    coaching_enriched = {
        "strengths": [
            {"pattern_id": s.get("pattern_id"), "message": s.get("message")}
            for s in strengths
        ],
        "focus": [
            {"pattern_id": f.get("pattern_id"), "message": f.get("message")}
            for f in focus
        ],
        "micro_experiment": {
            "title": micro.get("title"),
            "instruction": micro.get("instruction"),
            "success_marker": micro.get("success_marker"),
            "pattern_id": micro.get("pattern_id"),
            "evidence_span_ids": micro.get("evidence_span_ids"),
        },
    }

    # Evidence spans: include all, ensuring meeting_id is stamped on each
    enriched_spans = []
    for es in evidence_spans:
        span: dict = {
            "evidence_span_id": es.get("evidence_span_id"),
            "turn_start_id": es.get("turn_start_id"),
            "turn_end_id": es.get("turn_end_id"),
            "excerpt": es.get("excerpt"),
            "meeting_id": es.get("meeting_id") or meeting_id,
        }
        speaker_role = es.get("speaker_role")
        if speaker_role:
            span["speaker_role"] = speaker_role
        enriched_spans.append(span)

    return {
        "meeting_id": meeting_id,
        "meeting_type": ctx.get("meeting_type"),
        "analysis_id": parsed_json.get("meta", {}).get("analysis_id"),
        "target_speaker_name": run_fields.get(F_RUN_TARGET_SPEAKER_NAME),
        "target_speaker_label": run_fields.get(F_RUN_TARGET_SPEAKER_LABEL),
        "target_role": ctx.get("target_role"),
        "evaluation_summary": eval_summary,
        "pattern_snapshot": enriched_snapshot,
        "coaching_output": coaching_enriched,
        "evidence_spans": enriched_spans,
    }


def _patch_parsed_output(parsed: dict) -> dict:
    """
    Apply all post-LLM corrections to a parsed output dict.
    Returns a new deep-copied dict — does not mutate the input.

    Covers:
    - Strip numeric fields from conversational_balance (schema forbids them)
    - Backfill missing denominator_rule_id and min_required_threshold
    - Coerce zero-denominator evaluable patterns to insufficient_signal
    - Backfill null denominator_rule_id on not_evaluable patterns
    - Coerce legacy 'assigned' experiment status to 'proposed'
    """
    import copy as _copy
    parsed = _copy.deepcopy(parsed)

    # Strip numeric fields from conversational_balance — schema forbids them
    for snap in parsed.get("pattern_snapshot", []):
        if snap.get("pattern_id") == "conversational_balance":
            for field in ("numerator", "denominator", "ratio", "opportunity_count",
                          "opportunity_events", "opportunity_events_considered",
                          "opportunity_events_counted"):
                snap.pop(field, None)
        # Backfill required base fields the model sometimes omits
        snap.setdefault("denominator_rule_id", "qualitative_balance")
        snap.setdefault("min_required_threshold", None)

    # Coerce zero-denominator evaluable patterns to insufficient_signal
    for snap in parsed.get("pattern_snapshot", []):
        if (
            snap.get("evaluable_status") == "evaluable"
            and snap.get("pattern_id") != "conversational_balance"
            and snap.get("denominator") == 0
        ):
            snap["evaluable_status"] = "insufficient_signal"
            for field in ("numerator", "denominator", "ratio"):
                snap.pop(field, None)

    # Backfill null denominator_rule_id on not_evaluable patterns
    for snap in parsed.get("pattern_snapshot", []):
        if snap.get("denominator_rule_id") is None:
            snap["denominator_rule_id"] = "not_evaluable"

    # Coerce legacy 'assigned' experiment status to 'proposed'
    exp_track = parsed.get("experiment_tracking", {})
    active_exp = exp_track.get("active_experiment", {})
    if isinstance(active_exp, dict) and active_exp.get("status") == "assigned":
        active_exp["status"] = "proposed"

    return parsed


def _persist_run_fields(
    client: AirtableClient,
    *,
    transcript_record_id: str,
    run_request_record_id: Optional[str],
    baseline_pack_record_id: Optional[str],
    active_experiment_record_id: Optional[str] = None,
    request_payload: str,
    raw_output: str,
    parsed_json: Optional[dict],
    parse_ok: bool,
    schema_ok: bool,
    business_ok: bool,
    gate1_pass: bool,
    model_name: str,
    target_speaker_name: str,
    target_speaker_label: str,
    target_role: str,
    analysis_type: str,
    idempotency_key: str,
    coachee_id: str,
    user_record_id: Optional[str] = None,
) -> dict:
    """Create the run record in Airtable and return it."""
    fields: dict = {
        F_RUN_TRANSCRIPT: [transcript_record_id],
        F_RUN_MODEL_NAME: model_name,
        F_RUN_REQUEST_PAYLOAD: request_payload[:100_000],  # Airtable long text limit safety
        F_RUN_RAW_OUTPUT: raw_output[:100_000],  # Airtable long text limit safety
        F_RUN_PARSE_OK: parse_ok,
        F_RUN_SCHEMA_OK: schema_ok,
        F_RUN_BUSINESS_OK: business_ok,
        F_RUN_GATE1_PASS: gate1_pass,
        F_RUN_TARGET_SPEAKER_NAME: target_speaker_name,
        F_RUN_TARGET_SPEAKER_LABEL: target_speaker_label,
        F_RUN_TARGET_SPEAKER_ROLE: target_role,
        F_RUN_ANALYSIS_TYPE: analysis_type,
        F_RUN_IDEMPOTENCY_KEY: idempotency_key,
        F_RUN_COACHEE_ID: coachee_id,
    }

    if run_request_record_id:
        fields[F_RUN_RUN_REQUESTS] = [run_request_record_id]
    if baseline_pack_record_id:
        fields[F_RUN_BASELINE_PACK] = [baseline_pack_record_id]
    if active_experiment_record_id:
        fields[F_RUN_ACTIVE_EXPERIMENT] = [active_experiment_record_id]
    if user_record_id:
        fields["users"] = [user_record_id]

    if parsed_json:
        fields[F_RUN_PARSED_JSON] = _safe_json_dumps(parsed_json)
        fields[F_RUN_SCHEMA_VERSION_OUT] = parsed_json.get("schema_version")

        coaching = _extract_coaching_from_run(parsed_json)
        fields[F_RUN_FOCUS_PATTERN] = coaching["focus_pattern"]
        fields[F_RUN_MICRO_EXP_PATTERN] = coaching["micro_experiment_pattern"]
        fields[F_RUN_STRENGTHS_PATTERNS] = coaching["strengths_patterns"]
        fields[F_RUN_EXPERIMENT_ID_OUT] = coaching["experiment_id"]

        # Derive evaluated count from pattern_snapshot (source of truth) rather
        # than evaluation_summary, which the model sometimes gets wrong.
        snapshot = parsed_json.get("pattern_snapshot", [])
        fields[F_RUN_EVALUATED_COUNT] = sum(
            1 for ps in snapshot if ps.get("evaluable_status") == "evaluable"
        )
        fields[F_RUN_EVIDENCE_SPAN_COUNT] = len(parsed_json.get("evidence_spans", []))

        exp_tracking = parsed_json.get("experiment_tracking", {})
        active_exp = exp_tracking.get("active_experiment") or {}
        detection = exp_tracking.get("detection_in_this_meeting")
        fields[F_RUN_EXPERIMENT_STATUS_MODEL] = active_exp.get("status")
        if detection and isinstance(detection, dict):
            fields[F_RUN_ATTEMPT_MODEL] = detection.get("attempt")

    return client.create_run(fields)


# ── Worker 1: process_single_meeting_analysis ─────────────────────────────────

def process_single_meeting_analysis(
    run_request_id: str,
    client: Optional[AirtableClient] = None,
    system_prompt_override: Optional[str] = None,
    developer_message_override: Optional[str] = None,
) -> str:
    """
    Process a single_meeting analysis job.

    Args:
        run_request_id: Airtable record ID of the run_request.
        client: Optional pre-built AirtableClient (useful for testing).

    Returns:
        Run record ID.
    """
    if client is None:
        client = AirtableClient()

    # 1. Fetch run_request
    rr_record = client.get_run_request(run_request_id)
    rr_fields = _extract_fields(rr_record)
    logger.info("Processing run_request %s", run_request_id)

    transcript_links = _get_link_ids(rr_fields, "Transcript")
    if not transcript_links:
        raise ValueError(f"RunRequest {run_request_id} has no Transcript link.")
    transcript_record_id = transcript_links[0]

    target_speaker_name = rr_fields.get("Target Speaker Name", "")
    target_speaker_label = rr_fields.get("Target Speaker Label", "")
    target_role = rr_fields.get("Target Role", "")
    analysis_type = rr_fields.get("Analysis Type", "single_meeting")
    user_links = _get_link_ids(rr_fields, "User")
    user_record_id = user_links[0] if user_links else None
    coachee_id = user_record_id or ""

    active_exp_links = _get_link_ids(rr_fields, "Active Experiment")
    baseline_pack_links = _get_link_ids(rr_fields, "Baseline Pack")
    baseline_pack_record_id = baseline_pack_links[0] if baseline_pack_links else None
    active_exp_record_id = active_exp_links[0] if active_exp_links else None

    # Config
    config_name = None
    config_links = _get_link_ids(rr_fields, "Config")
    if config_links:
        cfg_record = client.get_record("config", config_links[0])
        cfg_fields = _extract_fields(cfg_record)
        config_name = cfg_fields.get("Config Name")

    config_version = CONFIG_VERSION

    # 2. Fetch + parse transcript
    transcript_record = client.get_transcript(transcript_record_id)
    tr_fields = _extract_fields(transcript_record)
    transcript_text = tr_fields.get("Transcript (extracted)") or tr_fields.get("Raw Transcript Text") or ""
    transcript_id_str = tr_fields.get("Transcript ID") or transcript_record_id
    meeting_type = tr_fields.get("Meeting Type") or "other"
    if meeting_type not in _VALID_MEETING_TYPES:
        logger.warning("Invalid meeting_type '%s' coerced to 'other'", meeting_type)
        meeting_type = "other"
    meeting_date = tr_fields.get("Meeting Date") or ""

    parsed = parse_transcript(
        data=transcript_text.encode("utf-8"),
        filename="transcript.txt",
        source_id=transcript_id_str,
    )

    # 3. Idempotency check — reuse only if the previous run passed Gate1.
    idem_key = make_run_idempotency_key(
        transcript_id_str, analysis_type, coachee_id,
        target_speaker_label, target_role, config_version,
    )
    existing_run = client.find_run_by_idempotency_key(idem_key)
    if existing_run:
        if _extract_fields(existing_run).get("Gate1 Pass"):
            logger.info("Idempotency hit, returning existing run %s", existing_run["id"])
            return existing_run["id"]
        else:
            logger.info(
                "Idempotency hit but run %s failed Gate1 — creating new run.",
                existing_run["id"],
            )

    # 4. Build memory block
    memory = _build_memory_for_user(client, user_record_id, active_exp_record_id)

    # 5. Build prompt
    prompt_payload = build_single_meeting_prompt(
        meeting_id=transcript_id_str,
        meeting_type=meeting_type,
        target_role=target_role,
        meeting_date=meeting_date,
        target_speaker_name=target_speaker_name,
        target_speaker_label=target_speaker_label,
        parsed_transcript=parsed,
        memory=memory,
    )

    # 6. Load system prompt + developer message
    sys_prompt = system_prompt_override or _load_system_prompt_from_config(client, config_links)
    dev_message = developer_message_override or _load_developer_message_from_config(client, config_links)

    # 6a. Mark run_request as processing so the frontend knows work has started
    client.update_run_request_status(run_request_id, "processing")

    # 6b. Call LLM
    openai_resp = call_llm(
        system_prompt=sys_prompt,
        developer_message=dev_message,
        user_message=prompt_payload.raw_user_message,
        model=_get_config_model(client, config_links),
        max_tokens=_get_config_max_tokens(client, config_links),
    )

    # 6c. Inject/fix meta fields the model may omit
    import json as _json
    _parsed_output = _json.loads(openai_resp.raw_text)
    if "meta" in _parsed_output:
        _parsed_output["meta"].setdefault("analysis_id", prompt_payload.meta.get("analysis_id"))
        _parsed_output["meta"].setdefault("analysis_type", prompt_payload.meta.get("analysis_type"))
        _parsed_output["meta"].setdefault("generated_at", prompt_payload.meta.get("generated_at"))
    # Fix experiment_tracking
    exp_track = _parsed_output.get("experiment_tracking", {})
    active_exp = exp_track.get("active_experiment", {})
    detection = exp_track.get("detection_in_this_meeting")

    # Coerce non-dict detection values to a no-attempt sentinel object
    active_status = exp_track.get("active_experiment", {}).get("status", "none")
    if active_status == "active":
        if not isinstance(detection, dict):
            exp_track["detection_in_this_meeting"] = {
                "experiment_id": exp_track.get("active_experiment", {}).get("experiment_id", "EXP-000000"),
                "attempt": "no",
                "count_attempts": 0,
                "evidence_span_ids": [],
            }
    else:
        exp_track["detection_in_this_meeting"] = {
            "experiment_id": "EXP-000000",
            "attempt": "no",
            "count_attempts": 0,
            "evidence_span_ids": [],
        }

    if active_exp:
        if active_exp.get("experiment_id") is None:
            exp_track["active_experiment"] = {"experiment_id": "EXP-000000", "status": "none"}
            exp_track["detection_in_this_meeting"] = None
            
    # Coerce missing evidence_span_ids on micro_experiment items
    coaching = _parsed_output.get("coaching_output", {})
    for item in coaching.get("micro_experiment", []):
        item.setdefault("evidence_span_ids", [])

    # Focus override safety gate: when an active experiment exists, force the
    # focus pattern_id to match the experiment's pattern_id. The system prompt
    # instructs the LLM to do this, but we enforce it as a backend guarantee.
    if active_exp_record_id and memory.active_experiment:
        expected_pattern = memory.active_experiment.get("pattern_id")
        focus_items = coaching.get("focus", [])
        if expected_pattern and focus_items:
            actual_pattern = focus_items[0].get("pattern_id")
            if actual_pattern != expected_pattern:
                logger.warning(
                    "Focus override: LLM returned '%s' but active experiment requires '%s'",
                    actual_pattern, expected_pattern,
                )
                focus_items[0]["pattern_id"] = expected_pattern
                # Replace the message with the coaching_note from the matching
                # pattern_snapshot entry so the text is relevant to the
                # overridden pattern.
                snapshot = _parsed_output.get("pattern_snapshot", [])
                match = next(
                    (ps for ps in snapshot
                     if ps.get("pattern_id") == expected_pattern),
                    None,
                )
                if match and match.get("coaching_note"):
                    focus_items[0]["message"] = match["coaching_note"]

    # Ensure rewrite_for_span_id is in evidence_span_ids for every pattern,
    # and that it is NOT in success_evidence_span_ids (it is always a failure).
    for ps in _parsed_output.get("pattern_snapshot", []):
        rewrite_span = ps.get("rewrite_for_span_id")
        es_ids = ps.get("evidence_span_ids", [])
        if rewrite_span and rewrite_span not in es_ids:
            es_ids.append(rewrite_span)
        success_ids = ps.get("success_evidence_span_ids", [])
        if rewrite_span and rewrite_span in success_ids:
            success_ids.remove(rewrite_span)

    _parsed_output = _patch_parsed_output(_parsed_output)

    # 6d. Clean up ASR artifacts in evidence_span excerpts and coaching blurbs.
    # This mutates _parsed_output in-place so the cleaned text is persisted
    # to Airtable, eliminating the need for LLM calls on every page load.
    if _CLEANUP_ENABLED:
        try:
            cleanup_parsed_json(_parsed_output)
        except Exception:
            logger.warning("Quote cleanup failed in worker; raw text will be persisted", exc_info=True)

    patched_raw = _json.dumps(_parsed_output, ensure_ascii=False)
    openai_resp = OpenAIResponse(
        parsed=_parsed_output,
        raw_text=patched_raw,
        model=openai_resp.model,
        prompt_tokens=openai_resp.prompt_tokens,
        completion_tokens=openai_resp.completion_tokens,
        total_tokens=openai_resp.total_tokens,
    )

    # 7. Gate1 validate
    gate1_result = gate1_validate(openai_resp.raw_text)

    # 8/9. Persist run
    run_record = _persist_run_fields(
        client,
        transcript_record_id=transcript_record_id,
        run_request_record_id=run_request_id,
        baseline_pack_record_id=baseline_pack_record_id,
        active_experiment_record_id=active_exp_record_id,
        request_payload=prompt_payload.raw_user_message,
        raw_output=openai_resp.raw_text,
        parsed_json=openai_resp.parsed,
        parse_ok=True,
        schema_ok=all(i.issue_code != "SCHEMA_VIOLATION" for i in gate1_result.issues),
        business_ok=gate1_result.passed,
        gate1_pass=gate1_result.passed,
        model_name=openai_resp.model,
        target_speaker_name=target_speaker_name,
        target_speaker_label=target_speaker_label,
        target_role=target_role,
        analysis_type=analysis_type,
        idempotency_key=idem_key,
        coachee_id=coachee_id,
        user_record_id=user_record_id or None,
    )
    run_record_id = run_record["id"]

    # Persist validation issues if any
    if gate1_result.issues:
        client.bulk_create_validation_issues(run_record_id, gate1_result.issues)

    # 8. Post-pass actions
    if gate1_result.passed:
        # Create experiment_event if active experiment was tracked
        exp_event_id = create_attempt_event_from_run(
            run_record_id,
            client=client,
            active_exp_record_id=active_exp_record_id,
        )
        if exp_event_id:
            client.update_run(run_record_id, {F_RUN_ATTEMPT_EVENT_CREATED: True})

    # Only propose experiments from standalone single meeting runs,
    # not from individual runs that are part of a baseline pack
    if not active_exp_record_id and not baseline_pack_record_id:
        exp_record_id = instantiate_experiment_from_run(
            run_record_id,
            client=client,
            user_record_id=user_record_id or None,
            baseline_pack_record_id=None,
        )
        if exp_record_id:
            client.update_run(run_record_id, {F_RUN_EXPERIMENT_INSTANTIATED: True})
            # Generate additional experiment options so the user has 3 to choose from
            if user_record_id:
                try:
                    process_next_experiment_suggestion(user_record_id, client=client)
                except Exception:
                    logger.warning(
                        "Failed to generate additional experiments after single meeting run %s",
                        run_record_id,
                    )

    # 10. Update run_request status
    new_status = "completed" if gate1_result.passed else "gate1_failed"
    client.update_run_request_status(run_request_id, new_status, run_record_id=run_record_id)

    logger.info("Completed run_request %s → run %s (gate1_pass=%s)", run_request_id, run_record_id, gate1_result.passed)
    return run_record_id


# ── Worker 2: process_baseline_pack_build ────────────────────────────────────

def process_baseline_pack_build(
    baseline_pack_id: str,
    client: Optional[AirtableClient] = None,
    system_prompt_override: Optional[str] = None,
    developer_message_override: Optional[str] = None,
) -> str:
    """
    Build the baseline pack analysis.

    Args:
        baseline_pack_id: Airtable record ID of the baseline_pack.

    Returns:
        Run record ID for the baseline pack run.
    """
    if client is None:
        client = AirtableClient()

    # 1. Fetch baseline_pack + items
    bp_record = client.get_baseline_pack(baseline_pack_id)
    bp_fields = _extract_fields(bp_record)
    bp_pack_id_str = bp_fields.get("Baseline Pack ID", "")
    target_role = bp_fields.get("Target Role") or "participant"
    speaker_label = bp_fields.get("Speaker Label") or ""
    user_links = _get_link_ids(bp_fields, "users")
    config_links = _get_link_ids(bp_fields, "Config") if "Config" in bp_fields else []

    # 1a. Idempotency check — prevent duplicate LLM calls if task is retried or
    # the build endpoint is called twice for the same pack.  Only reuse if the
    # previous run passed Gate1.
    idem_key = f"bp:{bp_pack_id_str}"
    existing_run = client.find_run_by_idempotency_key(idem_key)
    if existing_run and _extract_fields(existing_run).get("Gate1 Pass"):
        logger.info("Idempotency hit for baseline pack %s, returning existing run %s", baseline_pack_id, existing_run["id"])
        return existing_run["id"]

    items = client.get_baseline_pack_items(baseline_pack_id)
    
    if len(items) < 3:
        raise ValueError(f"BaselinePack {baseline_pack_id} has only {len(items)} items (need 3).")

    # 2. Ensure single_meeting runs exist for each item (idempotent sub-trigger)
    meeting_run_data: list[dict] = []
    meetings_meta: list[dict] = []

    for item in items[:3]:
        item_fields = _extract_fields(item)
        transcript_links = _get_link_ids(item_fields, "Transcript")
        run_links = _get_link_ids(item_fields, "Run")

        transcript_record_id = transcript_links[0] if transcript_links else None
        run_record_id = run_links[0] if run_links else None

        # If the linked run failed Gate1, discard it so we can create a fresh one.
        if run_record_id:
            linked_run = client.get_run(run_record_id)
            if not _extract_fields(linked_run).get("Gate1 Pass"):
                logger.info(
                    "Linked run %s for item %s failed Gate1 — unlinking and retrying.",
                    run_record_id, item["id"],
                )
                run_record_id = None

        if not run_record_id:
            # Look for an existing passing run by Transcript ID
            if transcript_record_id:
                tr_rec = client.get_record("transcripts", transcript_record_id)
                transcript_id_str = tr_rec.get("fields", {}).get("Transcript ID", "")
                if transcript_id_str:
                    formula = f"AND(FIND('{transcript_id_str}', {{Transcript ID (from Transcript)}}), {{Gate1 Pass}}=TRUE(), {{Analysis Type}}='single_meeting')"
                    existing_runs = client.search_records("runs", formula, max_records=1)
                    if existing_runs:
                        run_record_id = existing_runs[0]["id"]
                        client.update_record("baseline_pack_items", item["id"], {"Run": [run_record_id]})

            if not run_record_id:
                if not transcript_record_id:
                    raise ValueError(
                        f"BaselinePackItem {item['id']} has no Transcript link — cannot auto-run analysis."
                    )
                logger.info(
                    "No passing run found for item %s (transcript %s) — triggering inline single-meeting analysis.",
                    item["id"], transcript_record_id,
                )
                # Reuse a previous run_request for this transcript+pack if one
                # exists (e.g. from a prior failed attempt), otherwise create new.
                rr_formula = (
                    f"AND("
                    f"FIND('{transcript_record_id}', ARRAYJOIN({{Transcript}})), "
                    f"FIND('{baseline_pack_id}', ARRAYJOIN({{Baseline Pack}}))"
                    f")"
                )
                existing_rrs = client.search_records("run_requests", rr_formula, max_records=1)
                if existing_rrs:
                    rr_id = existing_rrs[0]["id"]
                    # Reset status so process_single_meeting_analysis treats it as new.
                    client.update_run_request_status(rr_id, "queued")
                    logger.info("Reusing existing run_request %s for transcript %s", rr_id, transcript_record_id)
                else:
                    rr_fields: dict = {
                        "Transcript": [transcript_record_id],
                        "Target Speaker Name": bp_fields.get("Target Speaker Name", ""),
                        "Target Speaker Label": speaker_label,
                        "Target Role": target_role,
                        "Analysis Type": "single_meeting",
                        "Status": "queued",
                        "Baseline Pack": [baseline_pack_id],
                    }
                    if user_links:
                        rr_fields["User"] = [user_links[0]]
                    if config_links:
                        rr_fields["Config"] = config_links

                    rr_record = client.create_run_request(rr_fields)
                    rr_id = rr_record["id"]

                try:
                    run_record_id = process_single_meeting_analysis(rr_id, client=client)
                except Exception as exc:
                    raise ValueError(
                        f"Auto single-meeting analysis failed for item {item['id']}: {exc}"
                    ) from exc

                # Link the newly created run back to the baseline_pack_item.
                client.update_baseline_pack_item(item["id"], {F_BPI_RUN: [run_record_id]})
                logger.info("Auto-linked run %s to item %s", run_record_id, item["id"])

        run_rec = client.get_run(run_record_id)
        run_fields = _extract_fields(run_rec)

        if not run_fields.get("Gate1 Pass"):
            raise ValueError(
                f"Run {run_record_id} for item {item['id']} did not pass Gate1. "
                "Cannot build baseline pack with failed run."
            )

        parsed_json_str = run_fields.get("Parsed JSON") or "{}"
        parsed_json = json.loads(parsed_json_str)

        # Build slim summary
        slim = _build_slim_meeting_summary(run_fields, parsed_json)
        meeting_run_data.append({
            "item_record_id": item["id"],
            "run_record_id": run_record_id,
            "transcript_record_id": transcript_record_id,
            "slim_summary": slim,
            "run_fields": run_fields,
            "parsed_json": parsed_json,
        })

        tr_fields_for_meta = {}
        if transcript_record_id:
            tr_rec = client.get_transcript(transcript_record_id)
            tr_fields_for_meta = _extract_fields(tr_rec)

        meetings_meta.append({
            "meeting_id": slim.get("meeting_id") or tr_fields_for_meta.get("Transcript ID", ""),
            "meeting_type": slim.get("meeting_type") or tr_fields_for_meta.get("Meeting Type", "other"),
            "target_speaker_name": slim.get("target_speaker_name", ""),
            "target_speaker_label": slim.get("target_speaker_label", speaker_label),
            "target_speaker_role": slim.get("target_role", target_role),
        })

    # Determine role / meeting type consistency
    roles = {m["target_speaker_role"] for m in meetings_meta}
    role_consistency = "consistent" if len(roles) == 1 else "mixed"
    mtypes = {m["meeting_type"] for m in meetings_meta}
    meeting_type_consistency = "consistent" if len(mtypes) == 1 else "mixed"

    # 3. Fetch the 3 slim summaries
    summaries = [mrd["slim_summary"] for mrd in meeting_run_data]

    # 4. Build baseline_pack prompt
    prompt_payload = build_baseline_pack_prompt(
        baseline_pack_id=bp_pack_id_str,
        pack_size=3,
        target_role=target_role,
        role_consistency=role_consistency,
        meeting_type_consistency=meeting_type_consistency,
        meetings_meta=meetings_meta,
        meeting_summaries=summaries,
    )

    # Get config (use first item's config if available — fall back to active)
    # Baseline packs use a dedicated system prompt optimised for synthesis.
    sys_prompt = system_prompt_override or load_baseline_system_prompt()
    dev_message = developer_message_override or _load_developer_message_from_config(client, config_links)

    # 5. Call LLM
    openai_resp = call_llm(
        system_prompt=sys_prompt,
        developer_message=dev_message,
        user_message=prompt_payload.raw_user_message,
        model=_get_config_model(client, config_links),
        max_tokens=_get_config_max_tokens(client, config_links),
    )

    import json as _json
    _parsed_output = _json.loads(openai_resp.raw_text)

    # Patch meta
    if "meta" in _parsed_output:
        _parsed_output["meta"].setdefault("analysis_type", "baseline_pack")
        _parsed_output["meta"].setdefault("generated_at", prompt_payload.meta.get("generated_at") if hasattr(prompt_payload, "meta") else None)

    # Override context consistency fields to booleans (schema requires bool, model returns strings)
    if "context" in _parsed_output:
        _parsed_output["context"]["role_consistency"] = (role_consistency == "consistent")
        _parsed_output["context"]["meeting_type_consistency"] = (meeting_type_consistency == "consistent")

    # Coerce numerator/denominator to integers (model sometimes returns floats)
    for _item in _parsed_output.get("pattern_snapshot", []):
        for _field in ("numerator", "denominator"):
            if isinstance(_item.get(_field), float):
                _item[_field] = round(_item[_field])
                
    # Coerce string detection values to None — schema requires null
    _exp_track = _parsed_output.get("experiment_tracking", {})
    if not isinstance(_exp_track.get("detection_in_this_meeting"), dict):
        _exp_track["detection_in_this_meeting"] = None

    # Ensure rewrite_for_span_id is in evidence_span_ids for every pattern,
    # and that it is NOT in success_evidence_span_ids (it is always a failure).
    for ps in _parsed_output.get("pattern_snapshot", []):
        rewrite_span = ps.get("rewrite_for_span_id")
        es_ids = ps.get("evidence_span_ids", [])
        if rewrite_span and rewrite_span not in es_ids:
            es_ids.append(rewrite_span)
        success_ids = ps.get("success_evidence_span_ids", [])
        if rewrite_span and rewrite_span in success_ids:
            success_ids.remove(rewrite_span)

    _parsed_output = _patch_parsed_output(_parsed_output)

    # 5b. Clean up ASR artifacts in baseline pack output
    if _CLEANUP_ENABLED:
        try:
            cleanup_parsed_json(_parsed_output)
        except Exception:
            logger.warning("Quote cleanup failed in baseline pack worker; raw text will be persisted", exc_info=True)

    patched_raw = _json.dumps(_parsed_output, ensure_ascii=False)
    openai_resp = OpenAIResponse(
        parsed=_parsed_output,
        raw_text=patched_raw,
        model=openai_resp.model,
        prompt_tokens=openai_resp.prompt_tokens,
        completion_tokens=openai_resp.completion_tokens,
        total_tokens=openai_resp.total_tokens,
    )

    # 6. Gate1 validate
    gate1_result = gate1_validate(openai_resp.raw_text)

    # Determine user_record_id from baseline pack users link
    user_record_id = user_links[0] if user_links else ""

    # 7. Persist run
    run_record = _persist_run_fields(
        client,
        transcript_record_id=meeting_run_data[0]["transcript_record_id"] or "",  # No direct transcript for BP run
        run_request_record_id=None,
        baseline_pack_record_id=baseline_pack_id,
        request_payload=prompt_payload.raw_user_message,
        raw_output=openai_resp.raw_text,
        parsed_json=openai_resp.parsed,
        parse_ok=True,
        schema_ok=all(i.issue_code != "SCHEMA_VIOLATION" for i in gate1_result.issues),
        business_ok=gate1_result.passed,
        gate1_pass=gate1_result.passed,
        model_name=openai_resp.model,
        target_speaker_name=meetings_meta[0].get("target_speaker_name", ""),
        target_speaker_label=meetings_meta[0].get("target_speaker_label", speaker_label),
        target_role=target_role,
        analysis_type="baseline_pack",
        idempotency_key=idem_key,
        coachee_id=user_record_id,
        user_record_id=user_record_id or None,       
    )
    run_record_id = run_record["id"]

    # Persist validation issues
    if gate1_result.issues:
        client.bulk_create_validation_issues(run_record_id, gate1_result.issues)

    new_status = "completed" if gate1_result.passed else "error"

    # Update baseline_pack status + last_run
    client.update_baseline_pack(baseline_pack_id, {
        F_BP_STATUS: new_status,
        F_BP_LAST_RUN: [run_record_id],
        F_BP_ROLE_CONSISTENCY: role_consistency,
        F_BP_MEETING_TYPE_CONSISTENCY: meeting_type_consistency,
    })

    # Update slim summaries on items
    for idx, mrd in enumerate(meeting_run_data):
        client.update_baseline_pack_item(mrd["item_record_id"], {
            F_BPI_MEETING_SUMMARY: _safe_json_dumps(mrd["slim_summary"]),
        })

    # 7b. Propose experiment from baseline pack output if gate1 passed
    if gate1_result.passed:
        # Set the user's Active Baseline Pack so the client dashboard can find it
        if user_record_id:
            client.update_user(user_record_id, {"Active Baseline Pack": [baseline_pack_id]})
            logger.info("Set Active Baseline Pack %s on user %s", baseline_pack_id, user_record_id)

        exp_record_id = instantiate_experiment_from_run(
            run_record_id,
            client=client,
            user_record_id=user_record_id or None,
            baseline_pack_record_id=baseline_pack_id,
        )
        if exp_record_id:
            client.update_run(run_record_id, {F_RUN_EXPERIMENT_INSTANTIATED: True})
            # Link proposed experiment to the baseline pack for reference
            client.update_baseline_pack(baseline_pack_id, {
                "Active Experiment": [exp_record_id],
            })
            # NOTE: do NOT auto-activate — coachee must accept from the queue.

            # Generate additional experiment options so the user has 3 to choose from
            if user_record_id:
                try:
                    process_next_experiment_suggestion(user_record_id, client=client)
                except Exception:
                    logger.warning(
                        "Failed to generate additional experiments after baseline pack %s",
                        baseline_pack_id,
                    )

    logger.info(
        "Completed baseline_pack build %s → run %s (gate1_pass=%s)",
        baseline_pack_id, run_record_id, gate1_result.passed,
    )
    return run_record_id


# ── Worker 3: instantiate_experiment_from_run ─────────────────────────────────

def instantiate_experiment_from_run(
    run_id: str,
    client: Optional[AirtableClient] = None,
    user_record_id: Optional[str] = None,
    baseline_pack_record_id: Optional[str] = None,
) -> Optional[str]:
    """
    Idempotent: create an experiment from the run's micro_experiment coaching output.

    Returns:
        Experiment record ID, or None if not applicable.
    """
    if client is None:
        client = AirtableClient()

    # Idempotency check
    existing = check_experiment_exists(client, run_id)
    if existing:
        return existing["id"]

    run_record = client.get_run(run_id)
    run_fields = _extract_fields(run_record)

    if not run_fields.get("Gate1 Pass"):
        logger.warning("Cannot instantiate experiment from failed run %s", run_id)
        return None

    parsed_json_str = run_fields.get("Parsed JSON") or "{}"
    parsed_json = json.loads(parsed_json_str)

    coaching = parsed_json.get("coaching_output", {})
    micro_list = coaching.get("micro_experiment", [])
    if not micro_list:
        logger.warning("Run %s has no micro_experiment in coaching_output", run_id)
        return None

    # Pick the micro_experiment matching the focus pattern; fall back to first.
    focus_list = coaching.get("focus", [])
    focus_pid = focus_list[0].get("pattern_id") if focus_list else None
    micro = next(
        (m for m in micro_list if m.get("pattern_id") == focus_pid),
        micro_list[0],
    ) if focus_pid else micro_list[0]
    exp_id = micro.get("experiment_id")
    title = micro.get("title", "")
    instruction = micro.get("instruction", "")
    success_marker = micro.get("success_marker", "")
    pattern_id = micro.get("pattern_id", "")

    if not exp_id or not pattern_id:
        logger.warning("Run %s micro_experiment missing experiment_id or pattern_id", run_id)
        return None

    fields: dict = {
        F_EXP_TITLE: title,
        F_EXP_INSTRUCTIONS: instruction,
        F_EXP_SUCCESS_CRITERIA: success_marker,
        F_EXP_SUCCESS_MARKER: success_marker,
        F_EXP_PATTERN_ID: pattern_id,
        F_EXP_STATUS: "proposed",
        F_EXP_PROPOSED_BY_RUN: [run_id],
        F_EXP_CREATED_FROM_RUN_ID: run_id,
    }
    if baseline_pack_record_id:
        fields[F_EXP_BASELINE_PACK] = [baseline_pack_record_id]
    if user_record_id:
        fields[F_EXP_USER] = [user_record_id]

    exp_record = client.create_experiment(fields)
    exp_record_id = exp_record["id"]

    # NOTE: do NOT set as active experiment here — coachee must explicitly
    # accept from the proposed queue. See POST /api/client/experiments/{id}/accept.
    logger.info("Proposed experiment %s from run %s", exp_record_id, run_id)
    return exp_record_id


# ── Worker 4: create_attempt_event_from_run ───────────────────────────────────

def create_attempt_event_from_run(
    run_id: str,
    client: Optional[AirtableClient] = None,
    active_exp_record_id: Optional[str] = None,
) -> Optional[str]:
    if client is None:
        client = AirtableClient()

    run_record = client.get_run(run_id)
    run_fields = _extract_fields(run_record)

    if not run_fields.get("Gate1 Pass"):
        logger.info("EE_DEBUG run %s: gate1 not passed", run_id)
        return None

    parsed_json_str = run_fields.get("Parsed JSON") or "{}"
    parsed_json = json.loads(parsed_json_str)

    exp_tracking = parsed_json.get("experiment_tracking", {})
    active_exp = exp_tracking.get("active_experiment") or {}
    detection = exp_tracking.get("detection_in_this_meeting")

    logger.info("EE_DEBUG run %s: detection=%s active_exp=%s", run_id, detection, active_exp)

    if not detection:
        logger.info("EE_DEBUG run %s: no detection, returning None", run_id)
        return None

    status = active_exp.get("status", "none")
    if status not in ("assigned", "active"):
        logger.info("EE_DEBUG run %s: status=%s not active/assigned, returning None", run_id, status)
        return None

    exp_record_id = active_exp_record_id
    if not exp_record_id:
        active_exp_links = _get_link_ids(run_fields, F_RUN_ACTIVE_EXPERIMENT)
        exp_record_id = active_exp_links[0] if active_exp_links else None
    if not exp_record_id:
        logger.info("EE_DEBUG run %s: no exp_record_id, returning None", run_id)
        return None

    logger.info("EE_DEBUG run %s: exp_record_id=%s", run_id, exp_record_id)

    # Idempotency check
    exp_id_in_run = active_exp.get("experiment_id")
    idem_key = make_experiment_event_key(run_id, exp_id_in_run)
    existing = client.find_experiment_event_by_idempotency_key(idem_key)
    if existing:
        logger.info("EE_DEBUG run %s: idempotency hit, event already exists", run_id)
        return existing["id"]

    logger.info("EE_DEBUG run %s: creating experiment event", run_id)

    # Extract detection fields
    attempt = detection.get("attempt")
    count_attempts = detection.get("count_attempts", 0)
    es_ids = detection.get("evidence_span_ids", [])

    # Get related records from run
    transcript_links = _get_link_ids(run_fields, "Transcript ID")
    user_links = _get_link_ids(run_fields, "users")
    baseline_pack_links = _get_link_ids(run_fields, "baseline_pack")
    transcript_record_id = transcript_links[0] if transcript_links else None
    user_record_id = user_links[0] if user_links else None
    baseline_pack_record_id = baseline_pack_links[0] if baseline_pack_links else None

    # For baseline pack runs, use the pack's Last Meeting Date rollup as the
    # anchor date — it represents the most recent of the three baseline meetings
    # and correctly precedes all post-baseline experiment events on the chart.
    # For single-meeting runs, use the transcript's own Meeting Date.
    meeting_date = None
    if baseline_pack_record_id:
        try:
            bp_rec = client.get_record("baseline_packs", baseline_pack_record_id)
            meeting_date = bp_rec.get("fields", {}).get("Last Meeting Date")
        except Exception as exc:
            logger.warning("Could not get baseline pack date for event: %s", exc)
    elif transcript_record_id:
        tr_rec = client.get_transcript(transcript_record_id)
        meeting_date = _extract_fields(tr_rec).get("Meeting Date")

    fields: dict = {
        F_EE_EXPERIMENT: [exp_record_id],
        F_EE_RUN: [run_id],
        F_EE_EVIDENCE_SPAN_IDS: json.dumps(es_ids),
        F_EE_IDEMPOTENCY_KEY: idem_key,
        F_EE_ATTEMPT_ENUM: attempt,
        F_EE_ATTEMPT_COUNT: count_attempts,
    }
    if transcript_record_id:
        fields[F_EE_TRANSCRIPT] = [transcript_record_id]
    if user_record_id:
        fields[F_EE_USER] = [user_record_id]
    if meeting_date:
        fields[F_EE_MEETING_DATE] = meeting_date

    event_record = client.create_experiment_event(fields)
    event_record_id = event_record["id"]

    # Update attempt tracking fields on the experiment record
    try:
        client.update_experiment_attempt_fields(
            exp_record_id,
            attempt=attempt,
            attempt_date=meeting_date,
        )
    except Exception as exc:
        logger.warning("Could not update experiment attempt fields: %s", exc)

    logger.info("Created experiment_event %s for run %s", event_record_id, run_id)
    return event_record_id


# ── Worker 5: process_next_experiment_suggestion ──────────────────────────────

_VALID_PATTERNS = {
    'agenda_clarity', 'objective_signaling', 'turn_allocation',
    'facilitative_inclusion', 'decision_closure', 'owner_timeframe_specification',
    'summary_checkback', 'question_quality', 'listener_response_quality',
    'conversational_balance',
}

MAX_PARKED = 3


def process_next_experiment_suggestion(
    user_record_id: str,
    client: Optional[AirtableClient] = None,
    just_parked_experiment_id: Optional[str] = None,
) -> Optional[str]:
    """
    Generate and propose up to 3 micro-experiments for a user after they
    complete or park their current experiment.

    Args:
        just_parked_experiment_id: If provided, the experiment that was just
            parked. Stored on proposed records so the options endpoint can
            demote it from the top-pick slot.

    - If user has 3 parked experiments (cap), skip generation entirely.
    - Otherwise, generate enough proposals so that
      (new proposals + parked count) = 3 total options.
    - Avoids repeating pattern_ids of parked experiments or the most recent
      completed/abandoned experiment.
    - Avoids reusing any past experiment title.
    - Creates proposed experiment records linked to the user.

    Returns:
        First experiment record ID created, or None if skipped.
    """
    if client is None:
        client = AirtableClient()

    # 0. Check existing proposed + parked counts — only generate the shortfall
    existing_proposed = client.get_proposed_experiments_for_user(user_record_id, max_records=3)
    proposed_count = len(existing_proposed)

    parked_records = client.get_parked_experiments_for_user(user_record_id)
    parked_count = len(parked_records)

    total_options = proposed_count + parked_count
    if total_options >= MAX_PARKED:
        logger.info(
            "process_next_experiment_suggestion: user %s already has %d options "
            "(%d proposed + %d parked) — skipping generation",
            user_record_id, total_options, proposed_count, parked_count,
        )
        return None

    num_to_generate = MAX_PARKED - total_options  # generate enough to reach 3 total

    # 1. Fetch up to 5 recent Gate1-passing runs for this user
    runs_formula = (
        f"AND("
        f"{{Coachee ID}} = '{user_record_id}', "
        f"{{Gate1 Pass}} = TRUE()"
        f")"
    )
    run_records = client.search_records("runs", runs_formula, max_records=5)

    # Exclude single_meeting sub-runs that belong to a baseline pack
    eligible_runs = [
        r for r in run_records
        if not (
            _extract_fields(r).get(F_RUN_ANALYSIS_TYPE) == "single_meeting"
            and _get_link_ids(_extract_fields(r), F_RUN_BASELINE_PACK)
        )
    ]

    if not eligible_runs:
        logger.info(
            "process_next_experiment_suggestion: no eligible runs for user %s — skipping",
            user_record_id,
        )
        return None

    # 2. Fetch past experiments (completed + abandoned + parked), most recent first
    user_rec = client.get_user(user_record_id)
    user_primary_id = _extract_fields(user_rec).get("User ID", "")

    past_exp_formula = (
        f"AND("
        f"FIND('{user_primary_id}', ARRAYJOIN({{User}})), "
        f"OR({{Status}} = 'completed', {{Status}} = 'abandoned', {{Status}} = 'parked')"
        f")"
    )
    past_exp_records = client.search_records("experiments", past_exp_formula, max_records=20)
    past_exp_records.sort(
        key=lambda x: _extract_fields(x).get(F_EXP_ENDED_AT) or "",
        reverse=True,
    )

    recent_pattern_id: Optional[str] = None
    past_titles: list[str] = []
    if past_exp_records:
        recent_pattern_id = _extract_fields(past_exp_records[0]).get(F_EXP_PATTERN_ID)
        past_titles = [
            _extract_fields(r).get(F_EXP_TITLE, "")
            for r in past_exp_records
            if _extract_fields(r).get(F_EXP_TITLE)
        ]

    # Collect pattern_ids of currently parked + proposed experiments — don't propose duplicates
    parked_pattern_ids: set[str] = set()
    for pr in parked_records:
        pid = _extract_fields(pr).get(F_EXP_PATTERN_ID)
        if pid:
            parked_pattern_ids.add(pid)
    for pr in existing_proposed:
        pid = _extract_fields(pr).get(F_EXP_PATTERN_ID)
        if pid:
            parked_pattern_ids.add(pid)

    # 3. Aggregate pattern scores and coaching notes across eligible runs
    pattern_scores: dict[str, list[float]] = {}
    # Collect coaching notes per pattern from recent analyses (most recent first)
    pattern_coaching_notes: dict[str, list[str]] = {}

    for r in eligible_runs:
        rf = _extract_fields(r)
        parsed_json_str = rf.get(F_RUN_PARSED_JSON) or "{}"
        try:
            parsed = json.loads(parsed_json_str)
            for p in parsed.get("pattern_snapshot", []):
                pid = p.get("pattern_id")
                if not pid:
                    continue
                if p.get("evaluable_status") == "evaluable":
                    ratio = p.get("ratio")
                    if ratio is not None:
                        pattern_scores.setdefault(pid, []).append(float(ratio))
                # Collect coaching notes regardless of evaluable status
                coaching_note = p.get("coaching_note")
                if coaching_note:
                    pattern_coaching_notes.setdefault(pid, []).append(coaching_note)
            # Also collect focus message from coaching_output
            coaching_output = parsed.get("coaching_output", {})
            for focus_item in (coaching_output.get("focus") or []):
                fpid = focus_item.get("pattern_id")
                fmsg = focus_item.get("message")
                if fpid and fmsg:
                    pattern_coaching_notes.setdefault(fpid, []).append(fmsg)
        except Exception:
            pass

    avg_scores = {
        pid: sum(vals) / len(vals)
        for pid, vals in pattern_scores.items()
    }
    sorted_patterns = sorted(avg_scores.items(), key=lambda x: x[1])

    # 4. Build user message with pattern scores, coaching notes, and exclusions
    pattern_lines = "\n".join(
        f"  {pid}: {score:.2f}" for pid, score in sorted_patterns
    ) or "  (no evaluable patterns available)"

    # Build coaching notes section — include up to 2 most recent notes per pattern
    coaching_notes_lines: list[str] = []
    for pid, _score in sorted_patterns:
        notes = pattern_coaching_notes.get(pid, [])
        if notes:
            # Deduplicate while preserving order (most recent first)
            seen: set[str] = set()
            unique_notes: list[str] = []
            for n in notes:
                if n not in seen:
                    seen.add(n)
                    unique_notes.append(n)
                if len(unique_notes) >= 2:
                    break
            coaching_notes_lines.append(f"  {pid}:")
            for n in unique_notes:
                coaching_notes_lines.append(f"    - {n}")

    coaching_notes_section = ""
    if coaching_notes_lines:
        coaching_notes_section = (
            "\nCoaching notes from recent meeting analyses (use these to tailor experiments to the coachee's specific behaviours):\n"
            + "\n".join(coaching_notes_lines)
        )

    # Build exclusion notes
    exclude_pattern_ids = set(parked_pattern_ids)
    if recent_pattern_id:
        exclude_pattern_ids.add(recent_pattern_id)

    avoid_patterns_note = ""
    if exclude_pattern_ids:
        avoid_patterns_note = (
            "\nDo NOT propose experiments for these pattern_ids (already in use or recently worked on):\n"
            + "\n".join(f"  - {pid}" for pid in sorted(exclude_pattern_ids))
        )

    avoid_titles_note = (
        "\nDo NOT reuse any of these past experiment titles:\n"
        + "\n".join(f"  - {t}" for t in past_titles[:10])
        if past_titles else ""
    )

    # Request extra experiments as buffer in case some fail validation
    llm_request_count = min(num_to_generate + 2, len(_VALID_PATTERNS) - len(exclude_pattern_ids))
    llm_request_count = max(llm_request_count, num_to_generate)

    user_message = (
        f"Propose {llm_request_count} micro-experiment(s) for this coachee.\n\n"
        f"Pattern scores (ratio 0-1, lower = more room to grow, based on recent meetings):\n"
        f"{pattern_lines}\n"
        f"{coaching_notes_section}"
        f"{avoid_patterns_note}"
        f"{avoid_titles_note}\n\n"
        f"Pick the {llm_request_count} patterns with the highest developmental impact that are not excluded above. "
        f"Each experiment MUST target a DIFFERENT pattern_id.\n"
        f"Propose specific, actionable micro-experiments targeting them, "
        f"grounded in the coaching notes above where available."
    )

    # 5. Load system prompt from file and model name from active config
    experiment_system_prompt = load_next_experiment_system_prompt()

    model_name: Optional[str] = None
    try:
        active_cfg = client.get_active_config()
        if active_cfg:
            model_name = active_cfg.get("fields", {}).get("Model Name")
    except Exception:
        pass

    # 6. Call OpenAI
    try:
        openai_resp = call_llm(
            system_prompt=experiment_system_prompt,
            developer_message="",
            user_message=user_message,
            model=model_name,
            max_tokens=600 * llm_request_count,
        )
    except Exception as exc:
        logger.error("process_next_experiment_suggestion: OpenAI call failed: %s", exc)
        return None

    # 7. Parse response — strip accidental markdown fences
    raw = openai_resp.raw_text.strip()
    if raw.startswith("```"):
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed_response = json.loads(raw)
    except Exception as exc:
        logger.error(
            "process_next_experiment_suggestion: JSON parse failed: %s | raw: %.500s",
            exc, raw,
        )
        return None

    # Normalise: if a single object was returned, wrap in a list
    if isinstance(parsed_response, dict):
        parsed_response = [parsed_response]

    if not isinstance(parsed_response, list):
        logger.error("process_next_experiment_suggestion: unexpected response type: %s", type(parsed_response))
        return None

    # 8. Validate and create experiment records (cap at num_to_generate valid proposals)
    required_keys = {"experiment_id", "title", "instruction", "success_marker", "pattern_id"}
    first_record_id: Optional[str] = None
    created_count = 0
    seen_patterns: set[str] = set(exclude_pattern_ids)

    for micro in parsed_response:
        if created_count >= num_to_generate:
            break
        missing = required_keys - micro.keys()
        if missing:
            logger.warning("process_next_experiment_suggestion: skipping proposal with missing fields %s", missing)
            continue
        if micro.get("pattern_id") not in _VALID_PATTERNS:
            logger.warning(
                "process_next_experiment_suggestion: skipping invalid pattern_id '%s'",
                micro.get("pattern_id"),
            )
            continue
        # Enforce distinct patterns
        if micro["pattern_id"] in seen_patterns:
            logger.warning("process_next_experiment_suggestion: skipping duplicate pattern_id '%s'", micro["pattern_id"])
            continue
        seen_patterns.add(micro["pattern_id"])

        # 9. Create proposed experiment record
        exp_fields: dict = {
            F_EXP_TITLE: micro["title"][:140],
            F_EXP_INSTRUCTIONS: micro["instruction"][:600],
            F_EXP_SUCCESS_CRITERIA: micro["success_marker"][:300],
            F_EXP_SUCCESS_MARKER: micro["success_marker"][:300],
            F_EXP_PATTERN_ID: micro["pattern_id"],
            F_EXP_STATUS: "proposed",
            F_EXP_USER: [user_record_id],
        }

        exp_record = client.create_experiment(exp_fields)
        exp_record_id = exp_record["id"]
        created_count += 1

        if first_record_id is None:
            first_record_id = exp_record_id

        logger.info(
            "process_next_experiment_suggestion: proposed experiment %s for user %s (pattern: %s)",
            exp_record_id, user_record_id, micro["pattern_id"],
        )

    if created_count < num_to_generate:
        logger.warning(
            "process_next_experiment_suggestion: only created %d of %d requested experiments for user %s",
            created_count, num_to_generate, user_record_id,
        )

    return first_record_id


# ── Private helpers ───────────────────────────────────────────────────────────

def _build_memory_for_user(
    client: AirtableClient,
    user_record_id: Optional[str],
    active_exp_record_id: Optional[str],
) -> MemoryBlock:
    """Build the memory block for a single_meeting prompt."""
    if not user_record_id:
        return MemoryBlock()

    user_rec = client.get_user(user_record_id)
    user_fields = _extract_fields(user_rec)

    # Check for active baseline pack
    bp_links = _get_link_ids(user_fields, "Active Baseline Pack")
    baseline_pack_id_str = None
    strengths: list[str] = []
    focus_pattern: Optional[str] = None

    if bp_links:
        bp_rec = client.get_baseline_pack(bp_links[0])
        bp_fields = _extract_fields(bp_rec)
        baseline_pack_id_str = bp_fields.get("Baseline Pack ID")

        # Try to get strengths/focus from the last baseline run
        last_run_links = _get_link_ids(bp_fields, "Last Run")
        if last_run_links:
            lr_rec = client.get_run(last_run_links[0])
            lr_fields = _extract_fields(lr_rec)
            strengths_json = lr_fields.get("Strengths Patterns") or "[]"
            try:
                strengths = json.loads(strengths_json)
            except (json.JSONDecodeError, TypeError):
                strengths = []
            focus_pattern = lr_fields.get("Focus Pattern")

    # Active experiment
    active_exp_data: Optional[dict] = None
    if active_exp_record_id:
        exp_rec = client.get_experiment(active_exp_record_id)
        exp_fields = _extract_fields(exp_rec)
        active_exp_data = {
            "experiment_id": exp_fields.get("Experiment ID"),
            "title": exp_fields.get("Title"),
            "instruction": exp_fields.get("Instruction") or exp_fields.get("Instructions"),
            "success_marker": exp_fields.get("Success Marker") or exp_fields.get("Success Criteria"),
            "pattern_id": exp_fields.get("Pattern ID"),
            "status": exp_fields.get("Status"),
        }

    return build_memory_block(
        baseline_pack_id=baseline_pack_id_str,
        strengths=strengths,
        focus_pattern=focus_pattern,
        active_experiment=active_exp_data,
        recent_snapshots=[],  # Populated via future enhancement
    )


def _load_system_prompt_from_config(client: AirtableClient, config_links: list[str]) -> str:
    """Load system prompt from the repo file (single source of truth).

    The client and config_links parameters are kept for backwards
    compatibility but are no longer used — the prompt is always read
    from system_prompt_v0_2_1.txt in the repo root.
    """
    return load_system_prompt()


def _load_developer_message_from_config(client: AirtableClient, config_links: list[str]) -> str:
    if config_links:
        try:
            cfg = client.get_record("config", config_links[0])
            tc = _extract_fields(cfg).get("Taxonomy Compact Block")
            if tc:
                return tc
        except Exception:
            pass
    try:
        cfg = client.get_active_config()
        if cfg:
            tc = cfg.get("fields", {}).get("Taxonomy Compact Block")
            if tc:
                return tc
    except Exception:
        pass
    return ""


def _get_config_model(client: AirtableClient, config_links: list[str]) -> Optional[str]:
    if config_links:
        try:
            cfg = client.get_record("config", config_links[0])
            model = _extract_fields(cfg).get("Model Name")
            if model:
                return model
        except Exception:
            pass
    # Fallback: try active config from Airtable
    try:
        cfg = client.get_active_config()
        if cfg:
            model = cfg.get("fields", {}).get("Model Name")
            if model:
                return model
    except Exception:
        pass
    return None


def _get_config_max_tokens(client: AirtableClient, config_links: list[str]) -> Optional[int]:
    if config_links:
        try:
            cfg = client.get_record("config", config_links[0])
            val = _extract_fields(cfg).get("Max Output Tokens")
            if val:
                return int(val)
        except Exception:
            pass
    try:
        cfg = client.get_active_config()
        if cfg:
            val = cfg.get("fields", {}).get("Max Output Tokens")
            if val:
                return int(val)
    except Exception:
        pass
    return None