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
from .models import MemoryBlock, ValidationIssue
from .openai_client import call_openai, load_system_prompt
from .prompt_builder import build_baseline_pack_prompt, build_memory_block, build_single_meeting_prompt
from .transcript_parser import parse_transcript

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
    """Build the slim meeting summary dict for baseline pack prompt."""
    ctx = parsed_json.get("context", {})
    eval_summary = parsed_json.get("evaluation_summary", {})
    pattern_snapshot = parsed_json.get("pattern_snapshot", [])
    coaching = parsed_json.get("coaching_output", {})

    # Compact pattern snapshot: only key fields
    slim_snapshot = [
        {
            "pattern_id": p.get("pattern_id"),
            "evaluable_status": p.get("evaluable_status"),
            "numerator": p.get("numerator"),
            "denominator": p.get("denominator"),
            "ratio": p.get("ratio"),
            "balance_assessment": p.get("balance_assessment"),
        }
        for p in pattern_snapshot
    ]

    # Compact coaching output
    micro = (coaching.get("micro_experiment") or [{}])[0]
    coaching_compact = {
        "focus_pattern_id": (coaching.get("focus") or [{}])[0].get("pattern_id"),
        "micro_experiment_title": micro.get("title"),
        "micro_experiment_instruction": micro.get("instruction"),
    }

    return {
        "meeting_id": ctx.get("meeting_id"),
        "meeting_type": ctx.get("meeting_type"),
        "analysis_id": parsed_json.get("meta", {}).get("analysis_id"),
        "target_speaker_name": run_fields.get(F_RUN_TARGET_SPEAKER_NAME),
        "target_speaker_label": run_fields.get(F_RUN_TARGET_SPEAKER_LABEL),
        "target_role": ctx.get("target_role"),
        "evaluation_summary": eval_summary,
        "pattern_snapshot": slim_snapshot,
        "coaching_output_compact": coaching_compact,
    }


def _persist_run_fields(
    client: AirtableClient,
    *,
    transcript_record_id: str,
    run_request_record_id: Optional[str],
    baseline_pack_record_id: Optional[str],
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
) -> dict:
    """Create the run record in Airtable and return it."""
    fields: dict = {
        F_RUN_TRANSCRIPT: [transcript_record_id],
        F_RUN_MODEL_NAME: model_name,
        F_RUN_REQUEST_PAYLOAD: request_payload,
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

    if parsed_json:
        fields[F_RUN_PARSED_JSON] = _safe_json_dumps(parsed_json)
        fields[F_RUN_SCHEMA_VERSION_OUT] = parsed_json.get("schema_version")

        coaching = _extract_coaching_from_run(parsed_json)
        fields[F_RUN_FOCUS_PATTERN] = coaching["focus_pattern"]
        fields[F_RUN_MICRO_EXP_PATTERN] = coaching["micro_experiment_pattern"]
        fields[F_RUN_STRENGTHS_PATTERNS] = coaching["strengths_patterns"]
        fields[F_RUN_EXPERIMENT_ID_OUT] = coaching["experiment_id"]

        eval_summary = parsed_json.get("evaluation_summary", {})
        fields[F_RUN_EVALUATED_COUNT] = len(eval_summary.get("patterns_evaluated", []))
        fields[F_RUN_EVIDENCE_SPAN_COUNT] = len(parsed_json.get("evidence_spans", []))

        exp_tracking = parsed_json.get("experiment_tracking", {})
        active_exp = exp_tracking.get("active_experiment") or {}
        detection = exp_tracking.get("detection_in_this_meeting")
        fields[F_RUN_EXPERIMENT_STATUS_MODEL] = active_exp.get("status")
        if detection:
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
    meeting_date = tr_fields.get("Meeting Date") or ""

    parsed = parse_transcript(
        data=transcript_text.encode("utf-8"),
        filename="transcript.txt",
        source_id=transcript_id_str,
    )

    # 3. Idempotency check
    idem_key = make_run_idempotency_key(
        transcript_id_str, analysis_type, coachee_id,
        target_speaker_label, target_role, config_version,
    )
    existing_run = client.find_run_by_idempotency_key(idem_key)
    if existing_run:
        logger.info("Idempotency hit, returning existing run %s", existing_run["id"])
        return existing_run["id"]

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

    # 6b. Call OpenAI
    openai_resp = call_openai(
        system_prompt=sys_prompt,
        developer_message=dev_message,
        user_message=prompt_payload.raw_user_message,
        model=_get_config_model(client, config_links),
        max_tokens=_get_config_max_tokens(client, config_links),
    )

    # 7. Gate1 validate
    gate1_result = gate1_validate(openai_resp.raw_text)

    # 8/9. Persist run
    parsed_json = openai_resp.parsed if gate1_result.passed else None

    run_record = _persist_run_fields(
        client,
        transcript_record_id=transcript_record_id,
        run_request_record_id=run_request_id,
        baseline_pack_record_id=None,
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
    )
    run_record_id = run_record["id"]

    # Persist validation issues if any
    if gate1_result.issues:
        client.bulk_create_validation_issues(run_record_id, gate1_result.issues)

    # 8. Post-pass actions
    if gate1_result.passed:
        # Create experiment_event if applicable
        exp_event_id = create_attempt_event_from_run(run_record_id, client=client)
        if exp_event_id:
            client.update_run(run_record_id, {F_RUN_ATTEMPT_EVENT_CREATED: True})

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

        if not run_record_id:
            raise ValueError(
                f"BaselinePackItem {item['id']} has no Run linked. "
                "Single-meeting runs must be completed before building the pack."
            )

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
    config_links = _get_link_ids(bp_fields, "Config") if "Config" in bp_fields else []
    sys_prompt = system_prompt_override or _load_system_prompt_from_config(client, config_links)
    dev_message = developer_message_override or _load_developer_message_from_config(client, config_links)

    # 5. Call OpenAI
    openai_resp = call_openai(
        system_prompt=sys_prompt,
        developer_message=dev_message,
        user_message=prompt_payload.raw_user_message,
        model=_get_config_model(client, config_links),
        max_tokens=_get_config_max_tokens(client, config_links),
    )

    # 6. Gate1 validate
    gate1_result = gate1_validate(openai_resp.raw_text)

    # Compute idempotency key (pack-level)
    idem_key = f"bp:{bp_pack_id_str}"

    # Determine user_record_id from baseline pack users link
    user_links = _get_link_ids(bp_fields, "users")
    user_record_id = user_links[0] if user_links else ""

    # 7. Persist run
    run_record = _persist_run_fields(
        client,
        transcript_record_id=meetings_meta[0].get("meeting_id", ""),  # No direct transcript for BP run
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

    # 7b. Instantiate experiment if gate1 passed
    if gate1_result.passed:
        exp_record_id = instantiate_experiment_from_run(
            run_record_id,
            client=client,
            user_record_id=user_record_id or None,
            baseline_pack_record_id=baseline_pack_id,
        )
        if exp_record_id:
            client.update_run(run_record_id, {F_RUN_EXPERIMENT_INSTANTIATED: True})
            client.update_baseline_pack(baseline_pack_id, {
                "Active Experiment": [exp_record_id],
            })
            if user_record_id:
                client.set_active_experiment_for_user(user_record_id, exp_record_id)

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

    micro = micro_list[0]
    exp_id = micro.get("experiment_id")
    title = micro.get("title", "")
    instruction = micro.get("instruction", "")
    success_marker = micro.get("success_marker", "")
    pattern_id = micro.get("pattern_id", "")

    if not exp_id or not pattern_id:
        logger.warning("Run %s micro_experiment missing experiment_id or pattern_id", run_id)
        return None

    fields: dict = {
        F_EXP_EXPERIMENT_ID: exp_id,
        F_EXP_TITLE: title,
        F_EXP_INSTRUCTIONS: instruction,
        F_EXP_SUCCESS_CRITERIA: success_marker,
        F_EXP_SUCCESS_MARKER: success_marker,
        F_EXP_PATTERN_ID: pattern_id,
        F_EXP_STATUS: "assigned",
        F_EXP_PROPOSED_BY_RUN: [run_id],
        F_EXP_CREATED_FROM_RUN_ID: run_id,
    }
    if baseline_pack_record_id:
        fields[F_EXP_BASELINE_PACK] = [baseline_pack_record_id]
    if user_record_id:
        fields[F_EXP_USER] = [user_record_id]

    exp_record = client.create_experiment(fields)
    exp_record_id = exp_record["id"]

    # Set as active experiment on user
    if user_record_id:
        client.set_active_experiment_for_user(user_record_id, exp_record_id)

    logger.info("Created experiment %s from run %s", exp_record_id, run_id)
    return exp_record_id


# ── Worker 4: create_attempt_event_from_run ───────────────────────────────────

def create_attempt_event_from_run(
    run_id: str,
    client: Optional[AirtableClient] = None,
) -> Optional[str]:
    """
    Idempotent: create an experiment_event from the run's detection output.

    Returns:
        ExperimentEvent record ID, or None if not applicable.
    """
    if client is None:
        client = AirtableClient()

    run_record = client.get_run(run_id)
    run_fields = _extract_fields(run_record)

    if not run_fields.get("Gate1 Pass"):
        return None

    parsed_json_str = run_fields.get("Parsed JSON") or "{}"
    parsed_json = json.loads(parsed_json_str)

    exp_tracking = parsed_json.get("experiment_tracking", {})
    active_exp = exp_tracking.get("active_experiment") or {}
    detection = exp_tracking.get("detection_in_this_meeting")

    if not detection:
        return None

    status = active_exp.get("status", "none")
    if status not in ("assigned", "active"):
        return None

    # Find active experiment record
    exp_id_in_run = active_exp.get("experiment_id")
    if not exp_id_in_run:
        return None

    # Look up experiment record
    exp_record = client.find_experiment_by_run_id(run_id)
    # If no experiment was created from THIS run, try finding by experiment_id field
    if not exp_record:
        records = client.search_records(
            "experiments",
            f"{{Experiment ID}} = '{exp_id_in_run}'",
            max_records=1,
        )
        exp_record = records[0] if records else None

    if not exp_record:
        logger.warning("Cannot find experiment record for experiment_id %s", exp_id_in_run)
        return None

    exp_record_id = exp_record["id"]

    # Idempotency check
    idem_key = make_experiment_event_key(run_id, exp_id_in_run)
    existing = client.find_experiment_event_by_idempotency_key(idem_key)
    if existing:
        return existing["id"]

    # Extract detection fields
    attempt = detection.get("attempt")
    count_attempts = detection.get("count_attempts", 0)
    es_ids = detection.get("evidence_span_ids", [])

    # Get related records from run
    transcript_links = _get_link_ids(run_fields, "Transcript ID")
    user_links = _get_link_ids(run_fields, "users")
    transcript_record_id = transcript_links[0] if transcript_links else None
    user_record_id = user_links[0] if user_links else None

    # Get meeting date from transcript
    meeting_date = None
    if transcript_record_id:
        tr_rec = client.get_transcript(transcript_record_id)
        meeting_date = _extract_fields(tr_rec).get("Meeting Date")

    fields: dict = {
        F_EE_EXPERIMENT: [exp_record_id],
        F_EE_RUN: [run_id],
        F_EE_DETECTION_MODEL: attempt,
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

    logger.info("Created experiment_event %s for run %s exp %s", event_record_id, run_id, exp_id_in_run)
    return event_record_id


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
    if config_links:
        try:
            cfg = client.get_record("config", config_links[0])
            sp = _extract_fields(cfg).get("System Prompt")
            if sp:
                return sp
        except Exception:
            pass
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
    # Fallback: empty developer message
    return ""


def _get_config_model(client: AirtableClient, config_links: list[str]) -> Optional[str]:
    if config_links:
        try:
            cfg = client.get_record("config", config_links[0])
            return _extract_fields(cfg).get("Model Name")
        except Exception:
            pass
    return None


def _get_config_max_tokens(client: AirtableClient, config_links: list[str]) -> Optional[int]:
    if config_links:
        try:
            cfg = client.get_record("config", config_links[0])
            val = _extract_fields(cfg).get("Max Output Tokens")
            return int(val) if val else None
        except Exception:
            pass
    return None
