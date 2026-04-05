"""
workers.py — Core job-processing functions (no queue runner).

Each function is self-contained and idempotent. The queue runner (Prompt 2)
calls these functions.
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
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
    F_EXP_RELATED_PATTERNS,
    F_EXP_JOURNEY_SUMMARY,
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
    F_RUN_EDITOR_CHANGELOG,
    F_RUN_EDITOR_TOKENS,
    F_RUN_STAGE2_CHANGELOG,
    F_RUN_STAGE2_TOKENS,
    F_RUN_STAGE2_RAW_OUTPUT,
    F_RUN_SCORING_VALID,
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
from .models import Gate1FailureError, MemoryBlock, ValidationIssue, OpenAIResponse
from .llm_client import call_llm
from .openai_client import load_baseline_system_prompt, load_next_experiment_system_prompt
from .prompt_builder import build_baseline_pack_prompt, build_memory_block, build_single_meeting_prompt
from .output_patches import patch_analysis_output
from .quote_cleanup import cleanup_parsed_json
from .transcript_parser import parse_transcript

# Feature flags
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
    return json.dumps(obj, ensure_ascii=False, indent=2)


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
    coaching = parsed_json.get("coaching", {})
    micro = coaching.get("micro_experiment", [{}])[0] if coaching.get("micro_experiment") else {}
    return {
        "focus_pattern": None,  # Deprecated in P2.4 — focus decoupled from experiments
        "micro_experiment_pattern": None,  # Deprecated in P2.4 — micro_experiment no longer has pattern_id
        "experiment_id": micro.get("experiment_id"),
        "micro_experiment_title": micro.get("title"),
        "micro_experiment_instruction": micro.get("instruction"),
        "micro_experiment_success_marker": micro.get("success_marker"),
    }


def _auto_correct_baseline_scores(
    parsed_output: dict,
    meeting_run_data: list[dict],
) -> list[ValidationIssue]:
    """Auto-correct baseline pack scores by recomputing weighted averages from sub-run data.

    For each evaluable pattern, computes:
        score = sum(sub_score_i * opp_count_i) / sum(opp_count_i)
    and corrects the LLM output in-place if it differs.

    Also validates that opportunity_count equals the sum across sub-runs.

    Returns list of correction issues (warning-level).
    """
    issues: list[ValidationIssue] = []

    # Collect (score, opportunity_count) per pattern from each sub-run
    pattern_data: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for mrd in meeting_run_data:
        slim = mrd.get("slim_summary", {})
        for ps in slim.get("pattern_snapshot", []):
            pid = ps.get("pattern_id")
            if ps.get("evaluable_status") != "evaluable" or pid is None:
                continue
            score = ps.get("score")
            opp = ps.get("opportunity_count", 0)
            if score is not None and opp > 0:
                pattern_data[pid].append((score, opp))

    # Validate and correct each pattern in the baseline output
    for idx, item in enumerate(parsed_output.get("pattern_snapshot", [])):
        pid = item.get("pattern_id")
        if item.get("evaluable_status") != "evaluable" or pid not in pattern_data:
            continue

        entries = pattern_data[pid]
        path = f"pattern_snapshot[{idx}]"

        # Weighted average score
        weighted_sum = sum(s * o for s, o in entries)
        total_opp = sum(o for _, o in entries)
        if total_opp == 0:
            continue

        expected_score = round(weighted_sum / total_opp, 4)
        actual_score = item.get("score")
        if actual_score is not None and abs(actual_score - expected_score) > 0.0005:
            item["score"] = expected_score
            issues.append(ValidationIssue(
                severity="warning",
                issue_code="BASELINE_SCORE_AUTOCORRECTED",
                path=f"{path}.score",
                message=(
                    f"score corrected from {actual_score} to {expected_score} "
                    f"(weighted avg = {weighted_sum:.4f} / {total_opp})."
                ),
            ))

        # Opportunity count sum
        actual_opp = item.get("opportunity_count")
        if actual_opp is not None and actual_opp != total_opp:
            item["opportunity_count"] = total_opp
            issues.append(ValidationIssue(
                severity="warning",
                issue_code="BASELINE_OPP_COUNT_AUTOCORRECTED",
                path=f"{path}.opportunity_count",
                message=(
                    f"opportunity_count corrected from {actual_opp} to {total_opp} "
                    f"(sum across {len(entries)} evaluable sub-runs)."
                ),
            ))

    return issues


def _build_slim_meeting_summary(run_fields: dict, parsed_json: dict) -> dict:
    """Build an enriched meeting summary dict for baseline pack prompt.

    Includes evidence_spans, per-pattern notes/coaching, and coaching messages
    so the baseline LLM can select and pass through real evidence rather than
    fabricating quotes.
    """
    ctx = parsed_json.get("context", {})
    eval_summary = parsed_json.get("evaluation_summary", {})
    pattern_snapshot = parsed_json.get("pattern_snapshot", [])
    coaching = parsed_json.get("coaching", {})
    evidence_spans = parsed_json.get("evidence_spans", [])

    meeting_id = ctx.get("meeting_id")

    # Build pattern_coaching lookup by pattern_id
    pattern_coaching_map: dict = {}
    for pc in coaching.get("pattern_coaching", []):
        pid = pc.get("pattern_id")
        if pid:
            pattern_coaching_map[pid] = pc

    # Enriched pattern snapshot: scoring fields + coaching from coaching.pattern_coaching
    enriched_snapshot = []
    for p in pattern_snapshot:
        item: dict = {
            "pattern_id": p.get("pattern_id"),
            "cluster_id": p.get("cluster_id"),
            "scoring_type": p.get("scoring_type"),
            "evaluable_status": p.get("evaluable_status"),
            "score": p.get("score"),
            "opportunity_count": p.get("opportunity_count"),
        }
        # Include scoring detail when present
        for key in ("evidence_span_ids", "success_evidence_span_ids",
                     "simple_count", "complex_count"):
            val = p.get(key)
            if val is not None:
                item[key] = val
        # Merge coaching fields from coaching.pattern_coaching
        pc = pattern_coaching_map.get(p.get("pattern_id"))
        if pc:
            for key in ("notes", "coaching_note", "suggested_rewrite",
                         "rewrite_for_span_id"):
                val = pc.get(key)
                if val is not None:
                    item[key] = val
        enriched_snapshot.append(item)

    # Enriched coaching output: include coaching themes, executive summary,
    # and micro_experiment for the baseline synthesis LLM.
    coaching_themes = coaching.get("coaching_themes") or []
    executive_summary = coaching.get("executive_summary") or ""
    micro = (coaching.get("micro_experiment") or [{}])[0]
    coaching_enriched: dict = {
        "executive_summary": executive_summary,
        "coaching_themes": coaching_themes,
        "micro_experiment": {
            "title": micro.get("title"),
            "instruction": micro.get("instruction"),
            "success_marker": micro.get("success_marker"),
            "related_patterns": micro.get("related_patterns", []),
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
        "coaching": coaching_enriched,
        "evidence_spans": enriched_spans,
    }


def _patch_parsed_output(parsed: dict) -> dict:
    """
    Apply all post-LLM corrections to a parsed output dict.
    Returns a new deep-copied dict — does not mutate the input.

    Covers:
    - Strip legacy numeric fields (numerator, denominator, ratio, tier)
    - Backfill missing denominator_rule_id and min_required_threshold
    - Coerce zero-opportunity evaluable patterns to insufficient_signal
    - Backfill null denominator_rule_id on not_evaluable patterns
    - Coerce legacy 'assigned' experiment status to 'proposed'
    """
    import copy as _copy
    parsed = _copy.deepcopy(parsed)

    # Strip legacy fields the model may still emit
    for snap in parsed.get("pattern_snapshot", []):
        for field in ("numerator", "denominator", "ratio", "tier"):
            snap.pop(field, None)
        # Backfill required base fields the model sometimes omits
        snap.setdefault("denominator_rule_id", "unknown")
        snap.setdefault("min_required_threshold", None)

    # Coerce zero-opportunity evaluable patterns to insufficient_signal
    for snap in parsed.get("pattern_snapshot", []):
        if (
            snap.get("evaluable_status") == "evaluable"
            and snap.get("opportunity_count") == 0
        ):
            snap["evaluable_status"] = "insufficient_signal"
            snap.pop("score", None)

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
    editor_changelog: Optional[list] = None,
    editor_tokens: Optional[int] = None,
    stage2_raw_output: Optional[str] = None,
    scoring_valid: Optional[bool] = None,
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
        fields[F_RUN_FOCUS_PATTERN] = ""  # Deprecated in P2.4
        fields[F_RUN_MICRO_EXP_PATTERN] = ""  # Deprecated in P2.4
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

    if editor_changelog:
        fields[F_RUN_STAGE2_CHANGELOG] = _safe_json_dumps(editor_changelog)
    if editor_tokens is not None:
        fields[F_RUN_STAGE2_TOKENS] = editor_tokens

    # Two-stage pipeline fields
    if stage2_raw_output:
        fields[F_RUN_STAGE2_RAW_OUTPUT] = stage2_raw_output[:100_000]
    if scoring_valid is not None:
        fields[F_RUN_SCORING_VALID] = scoring_valid

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

    # Config — try linked config first, fall back to active config
    config_name = None
    cfg_fields: dict = {}
    config_links = _get_link_ids(rr_fields, "Config")
    if config_links:
        cfg_record = client.get_record("config", config_links[0])
        cfg_fields = _extract_fields(cfg_record)
        config_name = cfg_fields.get("Config Name")
    if not cfg_fields:
        try:
            active_cfg = client.get_active_config()
            if active_cfg:
                cfg_fields = _extract_fields(active_cfg)
                config_name = cfg_fields.get("Config Name")
        except Exception:
            pass

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

    # Progress: transcript parsed
    try:
        client.update_run_request_progress(run_request_id, "Preparing analysis…")
    except Exception:
        pass  # non-blocking

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

    # 4. Build memory block (full — includes active experiment for Stage 2)
    memory = _build_memory_for_user(client, user_record_id, active_exp_record_id)

    # 5. Build prompt payload (transcript parsing, context assembly)
    # Stage 1 gets a stateless memory block (no active experiment)
    from .models import MemoryBlock as _MB
    stage1_memory = _MB(
        baseline_profile=memory.baseline_profile if memory else None,
        active_experiment=None,  # Stage 1 is stateless
    )
    prompt_payload = build_single_meeting_prompt(
        meeting_id=transcript_id_str,
        meeting_type=meeting_type,
        target_role=target_role,
        meeting_date=meeting_date,
        target_speaker_name=target_speaker_name,
        target_speaker_label=target_speaker_label,
        parsed_transcript=parsed,
        memory=stage1_memory,
    )

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 1: SCORING ONLY
    # ═══════════════════════════════════════════════════════════════════════════

    # 6. Load scoring system prompt + developer message (full taxonomy)
    from .openai_client import load_scoring_system_prompt
    sys_prompt = system_prompt_override or load_scoring_system_prompt()
    dev_message = developer_message_override or _load_developer_message_from_config(client, config_links)

    logger.info(
        "STAGE 1 [scoring] run_request=%s | sys_prompt=%d chars | "
        "dev_message=%d chars | user_message=%d chars",
        run_request_id, len(sys_prompt), len(dev_message),
        len(prompt_payload.raw_user_message),
    )

    # 6b. Mark run_request as processing
    client.update_run_request_status(run_request_id, "processing", progress_message="Scoring communication patterns…")

    # 6c. Call LLM — Stage 1 (scoring only)
    import json as _json
    stage1_resp = call_llm(
        system_prompt=sys_prompt,
        developer_message=dev_message,
        user_message=prompt_payload.raw_user_message,
        model=_get_config_model(client, config_links),
        max_tokens=_get_config_max_tokens(client, config_links),
    )

    # 6d. Apply post-LLM patches (scoring-only mode, no quote cleanup yet)
    stage1_parsed = _json.loads(stage1_resp.raw_text)
    stage1_parsed = patch_analysis_output(
        stage1_parsed,
        prompt_meta=prompt_payload.meta,
        scoring_only=True,
        cleanup_enabled=False,
    )
    stage1_raw = _json.dumps(stage1_parsed, ensure_ascii=False, indent=2)

    # 6e. Gate 1 validation (scoring-only)
    try:
        client.update_run_request_progress(run_request_id, "Validating scoring output…")
    except Exception:
        pass

    scoring_gate = gate1_validate(stage1_raw, mode="scoring_only")
    scoring_valid = scoring_gate.passed
    if scoring_gate.corrected_data:
        stage1_parsed = scoring_gate.corrected_data
        stage1_raw = _json.dumps(stage1_parsed, ensure_ascii=False, indent=2)

    if not scoring_valid:
        # Stage 1 failed — persist and abort
        logger.warning("Stage 1 scoring validation failed for run_request %s", run_request_id)
        run_record = _persist_run_fields(
            client,
            transcript_record_id=transcript_record_id,
            run_request_record_id=run_request_id,
            baseline_pack_record_id=baseline_pack_record_id,
            active_experiment_record_id=active_exp_record_id,
            request_payload=prompt_payload.raw_user_message,
            raw_output=stage1_raw,
            parsed_json=stage1_parsed,
            parse_ok=True,
            schema_ok=False,
            business_ok=False,
            gate1_pass=False,
            model_name=stage1_resp.model,
            target_speaker_name=target_speaker_name,
            target_speaker_label=target_speaker_label,
            target_role=target_role,
            analysis_type=analysis_type,
            idempotency_key=idem_key,
            coachee_id=coachee_id,
            user_record_id=user_record_id or None,
        )
        run_record_id = run_record["id"]
        try:
            client.update_run(run_record_id, {F_RUN_SCORING_VALID: False})
        except Exception:
            pass
        if scoring_gate.issues:
            client.bulk_create_validation_issues(run_record_id, scoring_gate.issues)
        client.update_run_request_status(run_request_id, "gate1_failed", run_record_id=run_record_id)
        return run_record_id

    logger.info("Stage 1 scoring validated for run_request %s", run_request_id)

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 2: COACHING SYNTHESIS
    # ═══════════════════════════════════════════════════════════════════════════

    try:
        client.update_run_request_progress(run_request_id, "Generating coaching feedback…")
    except Exception:
        pass

    # 7a. Build Stage 2 system prompt (with pattern definitions + experiment context)
    from .prompt_builder import build_stage2_system_prompt, build_stage2_user_message
    stage2_sys_prompt = build_stage2_system_prompt(memory)

    # 7b. Build Stage 2 user message (transcript + Stage 1 output)
    transcript_turns = prompt_payload.transcript_payload["turns"]
    stage2_user_msg = build_stage2_user_message(stage1_parsed, transcript_turns)

    logger.info(
        "STAGE 2 [coaching] run_request=%s | sys_prompt=%d chars | user_message=%d chars",
        run_request_id, len(stage2_sys_prompt), len(stage2_user_msg),
    )

    # 7c. Call LLM — Stage 2 (coaching)
    stage2_changelog = None
    stage2_tokens = None
    try:
        stage2_resp = call_llm(
            system_prompt=stage2_sys_prompt,
            developer_message="",
            user_message=stage2_user_msg,
            model=_get_config_model(client, config_links),
            max_tokens=_get_config_max_tokens(client, config_links),
        )
        stage2_parsed = stage2_resp.parsed
        stage2_raw = stage2_resp.raw_text
        stage2_tokens = stage2_resp.prompt_tokens + stage2_resp.completion_tokens

        logger.info(
            "Stage 2: %d prompt + %d completion tokens",
            stage2_resp.prompt_tokens, stage2_resp.completion_tokens,
        )

        # 7d. Merge Stage 1 scoring + Stage 2 coaching
        from .stage2_merge import merge_stage2_output
        merged_output, stage2_changelog = merge_stage2_output(stage1_parsed, stage2_parsed)

    except Exception as exc:
        logger.error("Stage 2 call/merge failed for run_request %s: %s", run_request_id, exc, exc_info=True)
        # Fall back: persist Stage 1 scoring only, mark as failed
        merged_output = stage1_parsed
        stage2_raw = ""
        stage2_changelog = [{"field": "stage2", "action": "failed", "reason": str(exc)}]

    # Progress: LLM calls complete
    try:
        client.update_run_request_progress(run_request_id, "Reviewing output quality…")
    except Exception:
        pass  # non-blocking

    # 7e. Apply coaching-related patches on merged output (deterministic, no LLM)
    merged_output = patch_analysis_output(
        merged_output,
        active_experiment=memory.active_experiment if memory else None,
        has_active_experiment=bool(active_exp_record_id),
        scoring_only=False,
        cleanup_enabled=False,
    )

    # 8. Gate 2 validation on merged output (full schema)
    merged_raw = _json.dumps(merged_output, ensure_ascii=False, indent=2)
    gate2_result = gate1_validate(merged_raw, mode="full")
    persisted_json = gate2_result.corrected_data or merged_output

    # 8b. Quote cleanup on final output (LLM call — cleans ASR artifacts in
    #     evidence span excerpts, including experiment detection spans from Stage 2)
    if _CLEANUP_ENABLED:
        try:
            from .quote_cleanup import cleanup_parsed_json
            cleanup_parsed_json(persisted_json)  # mutates in-place
        except Exception:
            logger.warning(
                "Quote cleanup failed for run_request %s; raw text will be persisted",
                run_request_id,
                exc_info=True,
            )

    # 9. Persist run
    run_record = _persist_run_fields(
        client,
        transcript_record_id=transcript_record_id,
        run_request_record_id=run_request_id,
        baseline_pack_record_id=baseline_pack_record_id,
        active_experiment_record_id=active_exp_record_id,
        request_payload=prompt_payload.raw_user_message,
        raw_output=stage1_raw,
        parsed_json=persisted_json,
        parse_ok=True,
        schema_ok=all(i.issue_code != "SCHEMA_VIOLATION" for i in gate2_result.issues),
        business_ok=gate2_result.passed,
        gate1_pass=gate2_result.passed,
        model_name=stage1_resp.model,
        target_speaker_name=target_speaker_name,
        target_speaker_label=target_speaker_label,
        target_role=target_role,
        analysis_type=analysis_type,
        idempotency_key=idem_key,
        coachee_id=coachee_id,
        user_record_id=user_record_id or None,
        editor_changelog=stage2_changelog,
        editor_tokens=stage2_tokens,
        stage2_raw_output=stage2_raw,
        scoring_valid=scoring_valid,
    )
    run_record_id = run_record["id"]

    # Persist validation issues if any
    if gate2_result.issues:
        client.bulk_create_validation_issues(run_record_id, gate2_result.issues)

    # 8. Post-pass actions
    if gate2_result.passed:
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
    new_status = "completed" if gate2_result.passed else "gate1_failed"
    client.update_run_request_status(run_request_id, new_status, run_record_id=run_record_id)

    logger.info("Completed run_request %s → run %s (gate1_pass=%s)", run_request_id, run_record_id, gate2_result.passed)
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
    # Sub-runs are fully independent — run them concurrently.
    try:
        client.update_baseline_pack_progress(
            baseline_pack_id, "Analyzing 3 meetings concurrently…"
        )
    except Exception:
        pass  # non-blocking

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _process_baseline_item(
        item: dict,
        item_idx: int,
    ) -> tuple[dict, dict]:
        """Process a single baseline pack item. Thread-safe — uses its own AirtableClient."""
        thread_client = AirtableClient()

        item_fields = _extract_fields(item)
        transcript_links = _get_link_ids(item_fields, "Transcript")
        run_links = _get_link_ids(item_fields, "Run")

        transcript_record_id = transcript_links[0] if transcript_links else None
        run_record_id = run_links[0] if run_links else None

        # If the linked run failed Gate1, discard it so we can create a fresh one.
        if run_record_id:
            linked_run = thread_client.get_run(run_record_id)
            if not _extract_fields(linked_run).get("Gate1 Pass"):
                logger.info(
                    "Linked run %s for item %s failed Gate1 — unlinking and retrying.",
                    run_record_id, item["id"],
                )
                run_record_id = None

        if not run_record_id:
            # Look for an existing passing run by Transcript ID
            if transcript_record_id:
                tr_rec = thread_client.get_record("transcripts", transcript_record_id)
                transcript_id_str = tr_rec.get("fields", {}).get("Transcript ID", "")
                if transcript_id_str:
                    formula = f"AND(FIND('{transcript_id_str}', {{Transcript ID (from Transcript)}}), {{Gate1 Pass}}=TRUE(), {{Analysis Type}}='single_meeting')"
                    existing_runs = thread_client.search_records("runs", formula, max_records=1)
                    if existing_runs:
                        run_record_id = existing_runs[0]["id"]
                        thread_client.update_record("baseline_pack_items", item["id"], {"Run": [run_record_id]})

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
                existing_rrs = thread_client.search_records("run_requests", rr_formula, max_records=1)
                if existing_rrs:
                    rr_id = existing_rrs[0]["id"]
                    # Reset status so process_single_meeting_analysis treats it as new.
                    thread_client.update_run_request_status(rr_id, "queued")
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

                    rr_record = thread_client.create_run_request(rr_fields)
                    rr_id = rr_record["id"]

                try:
                    run_record_id = process_single_meeting_analysis(rr_id, client=thread_client)
                except Exception as exc:
                    # Mark the run_request as error so it doesn't remain stuck
                    # in "processing" status forever.
                    try:
                        thread_client.update_run_request_status(
                            rr_id, "error", error=str(exc)[:2000]
                        )
                    except Exception:
                        logger.warning(
                            "Failed to update run_request %s status to error", rr_id
                        )
                    raise ValueError(
                        f"Auto single-meeting analysis failed for item {item['id']}: {exc}"
                    ) from exc

                # Link the newly created run back to the baseline_pack_item.
                thread_client.update_baseline_pack_item(item["id"], {F_BPI_RUN: [run_record_id]})
                logger.info("Auto-linked run %s to item %s", run_record_id, item["id"])

        run_rec = thread_client.get_run(run_record_id)
        run_fields = _extract_fields(run_rec)

        if not run_fields.get("Gate1 Pass"):
            raise Gate1FailureError(
                f"Run {run_record_id} for item {item['id']} did not pass Gate1. "
                "Cannot build baseline pack with failed run."
            )

        parsed_json_str = run_fields.get("Parsed JSON") or "{}"
        parsed_json = json.loads(parsed_json_str)

        # Build slim summary
        slim = _build_slim_meeting_summary(run_fields, parsed_json)
        run_data_entry = {
            "item_record_id": item["id"],
            "run_record_id": run_record_id,
            "transcript_record_id": transcript_record_id,
            "slim_summary": slim,
            "run_fields": run_fields,
            "parsed_json": parsed_json,
        }

        tr_fields_for_meta = {}
        if transcript_record_id:
            tr_rec = thread_client.get_transcript(transcript_record_id)
            tr_fields_for_meta = _extract_fields(tr_rec)

        meta_entry = {
            "meeting_id": slim.get("meeting_id") or tr_fields_for_meta.get("Transcript ID", ""),
            "meeting_type": slim.get("meeting_type") or tr_fields_for_meta.get("Meeting Type", "other"),
            "target_speaker_name": slim.get("target_speaker_name", ""),
            "target_speaker_label": slim.get("target_speaker_label", speaker_label),
            "target_speaker_role": slim.get("target_role", target_role),
        }

        return run_data_entry, meta_entry

    # Run all 3 sub-runs concurrently
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_process_baseline_item, item, idx): idx
            for idx, item in enumerate(items[:3])
        }
        results: list[Optional[tuple[dict, dict]]] = [None, None, None]
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()  # raises if sub-run failed

    meeting_run_data = [r[0] for r in results]  # type: ignore[index]
    meetings_meta = [r[1] for r in results]  # type: ignore[index]

    # Determine role / meeting type consistency
    roles = {m["target_speaker_role"] for m in meetings_meta}
    role_consistency = "consistent" if len(roles) == 1 else "mixed"
    mtypes = {m["meeting_type"] for m in meetings_meta}
    meeting_type_consistency = "consistent" if len(mtypes) == 1 else "mixed"

    # 3. Fetch the 3 slim summaries
    summaries = [mrd["slim_summary"] for mrd in meeting_run_data]

    # Progress: synthesizing
    try:
        client.update_baseline_pack_progress(baseline_pack_id, "Synthesizing patterns across meetings…")
    except Exception:
        pass  # non-blocking

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

    # 5. Debug: log taxonomy content being sent to LLM
    _dev_pattern_ids = [m.group(1) for m in re.finditer(r'### BEGIN:PATTERN:(\w+) ###', dev_message)]
    logger.info(
        "TAXONOMY DEBUG [baseline_pack] baseline_pack_id=%s | sys_prompt=%d chars | "
        "dev_message=%d chars | %d patterns: %s | has CORE_RULES=%s | "
        "user_message=%d chars | %d meeting_summaries",
        prompt_payload.context.get("baseline_pack_id") if isinstance(prompt_payload.context, dict) else "?",
        len(sys_prompt), len(dev_message),
        len(_dev_pattern_ids), _dev_pattern_ids,
        "### BEGIN:CORE_RULES ###" in dev_message,
        len(prompt_payload.raw_user_message),
        len(summaries),
    )

    # Progress: calling LLM for baseline synthesis
    try:
        client.update_baseline_pack_progress(baseline_pack_id, "Generating baseline assessment…")
    except Exception:
        pass  # non-blocking

    # 5b. Call LLM
    # Baseline packs produce ~10-12 k tokens of JSON (9 patterns + coaching).
    # The global default (8 192) is too tight and causes finish_reason=length
    # truncations.  Use 16 384 unless an Airtable config override is set.
    openai_resp = call_llm(
        system_prompt=sys_prompt,
        developer_message=dev_message,
        user_message=prompt_payload.raw_user_message,
        model=_get_config_model(client, config_links),
        max_tokens=_get_config_max_tokens(client, config_links) or 16384,
    )

    import json as _json
    _parsed_output = _json.loads(openai_resp.raw_text)

    # Patch meta
    if "meta" in _parsed_output:
        _parsed_output["meta"].setdefault("analysis_id", prompt_payload.meta.get("analysis_id"))
        _parsed_output["meta"].setdefault("analysis_type", "baseline_pack")
        _parsed_output["meta"].setdefault("generated_at", prompt_payload.meta.get("generated_at") if hasattr(prompt_payload, "meta") else None)

    # Override context consistency fields to booleans (schema requires bool, model returns strings)
    if "context" in _parsed_output:
        _parsed_output["context"]["role_consistency"] = (role_consistency == "consistent")
        _parsed_output["context"]["meeting_type_consistency"] = (meeting_type_consistency == "consistent")

    # Coerce opportunity_count to integer (model sometimes returns floats)
    for _item in _parsed_output.get("pattern_snapshot", []):
        if isinstance(_item.get("opportunity_count"), float):
            _item["opportunity_count"] = round(_item["opportunity_count"])
                
    # Coerce string detection values to None — schema requires null
    _exp_track = _parsed_output.get("experiment_tracking", {})
    if not isinstance(_exp_track.get("detection_in_this_meeting"), dict):
        _exp_track["detection_in_this_meeting"] = None

    # Apply output patches before stripping so patching can normalise
    # malformed structures (e.g. missing fields) before we iterate them.
    _parsed_output = _patch_parsed_output(_parsed_output)

    # ── Strip evidence-span arrays from baseline-pack aggregate ─────────
    # The LLM uses spans as *input* (in meeting_summaries) to write grounded
    # prose, but the *output* span ID arrays have namespace collisions
    # (ES-001 from meeting A vs meeting B) and are never resolved to quotes
    # at the aggregate level (the API already returns quotes: []).
    # Strip them so Gate1 doesn't choke on duplicates or dangling refs.
    for ps in _parsed_output.get("pattern_snapshot", []):
        if not isinstance(ps, dict):
            continue
        ps["evidence_span_ids"] = []
        ps["success_evidence_span_ids"] = []

    # Strip coaching rewrite span refs (namespace collision risk)
    for pc in (_parsed_output.get("coaching", {}) or {}).get("pattern_coaching", []):
        if not isinstance(pc, dict):
            continue
        pc["rewrite_for_span_id"] = None

    # Strip micro_experiment evidence spans; filter out malformed (non-dict) items
    _coaching = _parsed_output.get("coaching", {}) or {}
    _micro_list = _coaching.get("micro_experiment", [])
    _malformed = [me for me in _micro_list if not isinstance(me, dict)]
    if _malformed:
        logger.warning(
            "Baseline pack %s: %d malformed micro_experiment item(s) "
            "(non-dict) — filtering out. Fallback experiment generation "
            "will be used.",
            bp_pack_id_str, len(_malformed),
        )
        _micro_list = [me for me in _micro_list if isinstance(me, dict)]
        _coaching["micro_experiment"] = _micro_list
    for me in _micro_list:
        me["evidence_span_ids"] = []

    _parsed_output["evidence_spans"] = []

    # Auto-correct baseline scores from sub-run data (deterministic weighted averages)
    baseline_corrections = _auto_correct_baseline_scores(_parsed_output, meeting_run_data)
    if baseline_corrections:
        logger.info(
            "Baseline pack %s: %d score corrections applied.",
            baseline_pack_id, len(baseline_corrections),
        )

    # NOTE: cleanup_parsed_json is intentionally NOT called for baseline packs.
    # Evidence spans are already cleaned in the per-meeting sub-runs; running
    # cleanup again is wasteful (extra LLM call) and can corrupt span text.

    patched_raw = _json.dumps(_parsed_output, ensure_ascii=False, indent=2)
    openai_resp = OpenAIResponse(
        parsed=_parsed_output,
        raw_text=patched_raw,
        model=openai_resp.model,
        prompt_tokens=openai_resp.prompt_tokens,
        completion_tokens=openai_resp.completion_tokens,
        total_tokens=openai_resp.total_tokens,
    )

    # Progress: reviewing output
    try:
        client.update_baseline_pack_progress(baseline_pack_id, "Reviewing output quality…")
    except Exception:
        pass  # non-blocking

    # 6. Gate1 validate (may auto-correct scores in-place)
    gate1_result = gate1_validate(openai_resp.raw_text)
    # Merge baseline score corrections into Gate1 result
    if baseline_corrections:
        gate1_result.issues.extend(baseline_corrections)
        # Ensure corrected data reflects baseline auto-corrections
        if gate1_result.corrected_data is None:
            gate1_result.corrected_data = openai_resp.parsed
    persisted_json = gate1_result.corrected_data or openai_resp.parsed

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
        parsed_json=persisted_json,
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
    exp_record_id = None
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

    # 7c. Fallback: if primary experiment instantiation failed (malformed
    # micro_experiment, gate1 failure, etc.), generate experiments from
    # coaching history so the coachee always has a proposed experiment.
    if not exp_record_id and user_record_id:
        logger.info(
            "Baseline pack %s: primary experiment instantiation failed — "
            "using fallback experiment generation for user %s",
            baseline_pack_id, user_record_id,
        )
        try:
            process_next_experiment_suggestion(user_record_id, client=client)
        except Exception:
            logger.warning(
                "Fallback experiment generation also failed for baseline pack %s",
                baseline_pack_id,
                exc_info=True,
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

    coaching = parsed_json.get("coaching", {})
    micro_list = coaching.get("micro_experiment", [])
    if not micro_list:
        logger.warning("Run %s has no micro_experiment in coaching", run_id)
        return None

    # Always take the first micro_experiment (focus matching removed in P2.4)
    micro = micro_list[0]
    exp_id = micro.get("experiment_id")
    title = micro.get("title", "")
    instruction = micro.get("instruction", "")
    success_marker = micro.get("success_marker", "")
    related_patterns = micro.get("related_patterns", [])

    if not exp_id:
        logger.warning("Run %s micro_experiment missing experiment_id", run_id)
        return None

    fields: dict = {
        F_EXP_TITLE: title,
        F_EXP_INSTRUCTIONS: instruction,
        F_EXP_SUCCESS_CRITERIA: success_marker,
        F_EXP_SUCCESS_MARKER: success_marker,
        F_EXP_PATTERN_ID: "",  # Deprecated in P2.4; kept empty for backward compat
        F_EXP_RELATED_PATTERNS: json.dumps(related_patterns),
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

MAX_PARKED = 3
MAX_COACHING_HISTORY_MEETINGS = 3
MAX_EXPERIMENT_HISTORY = 5


# ── Shared data-fetching helpers ──────────────────────────────────────────────

def _fetch_recent_coaching_data(
    client: AirtableClient,
    user_record_id: str,
    max_runs: int = 5,
) -> tuple[
    list[tuple[str, list]],                          # coaching_themes_by_run
    list[tuple[str, str]],                           # executive_summaries_by_run
    list[tuple[str, str, int, Optional[str], Optional[str]]],  # experiment_progress (date, attempt, count, note, exp_id)
    list[dict],                                      # eligible_run_records (raw)
]:
    """Fetch recent Gate1-passing runs and extract coaching data.

    Returns coaching themes, executive summaries, and experiment progress
    extracted from each eligible run's Parsed JSON. Used by both
    ``_build_memory_for_user`` (coachee history) and
    ``process_next_experiment_suggestion`` (experiment proposals).

    Eligible runs: standalone single_meeting runs and baseline_pack synthesis
    runs. Baseline pack sub-runs (single_meeting with a baseline_pack link)
    are excluded.
    """
    runs_formula = (
        f"AND("
        f"{{Coachee ID}} = '{user_record_id}', "
        f"{{Gate1 Pass}} = TRUE()"
        f")"
    )
    run_records = client.search_records("runs", runs_formula, max_records=max_runs)

    # Exclude single_meeting sub-runs that belong to a baseline pack
    eligible_runs = [
        r for r in run_records
        if not (
            _extract_fields(r).get(F_RUN_ANALYSIS_TYPE) == "single_meeting"
            and _get_link_ids(_extract_fields(r), F_RUN_BASELINE_PACK)
        )
    ]

    coaching_themes_by_run: list[tuple[str, list]] = []
    executive_summaries_by_run: list[tuple[str, str]] = []
    experiment_progress: list[tuple[str, str, int, Optional[str], Optional[str]]] = []

    for r in eligible_runs:
        rf = _extract_fields(r)
        parsed_json_str = rf.get(F_RUN_PARSED_JSON) or "{}"
        meeting_date = rf.get("Meeting Date") or rf.get("Created At") or "unknown"
        try:
            parsed = json.loads(parsed_json_str)
            # Coaching themes
            themes = (parsed.get("coaching", {}) or {}).get("coaching_themes", [])
            if themes:
                coaching_themes_by_run.append((meeting_date, themes))
            # Executive summary
            exec_summary = (parsed.get("coaching", {}) or {}).get("executive_summary")
            if exec_summary:
                executive_summaries_by_run.append((meeting_date, exec_summary))
            # Experiment progress (if run had active experiment)
            exp_tracking = parsed.get("experiment_tracking", {})
            detection = exp_tracking.get("detection_in_this_meeting") if exp_tracking else None
            if detection:
                exp_coaching = (parsed.get("coaching", {}) or {}).get("experiment_coaching")
                coaching_note = exp_coaching.get("coaching_note") if exp_coaching else None
                det_exp_id = detection.get("experiment_id")
                experiment_progress.append((
                    meeting_date,
                    detection.get("attempt", "unknown"),
                    detection.get("count_attempts", 0),
                    coaching_note,
                    det_exp_id,
                ))
        except Exception:
            pass

    logger.info(
        "_fetch_recent_coaching_data: user=%s | %d total runs, %d eligible, "
        "%d with themes, %d with exec summaries",
        user_record_id, len(run_records), len(eligible_runs),
        len(coaching_themes_by_run), len(executive_summaries_by_run),
    )

    return coaching_themes_by_run, executive_summaries_by_run, experiment_progress, eligible_runs


def _fetch_experiment_history(
    client: AirtableClient,
    user_record_id: str,
    max_experiments: int = 20,
) -> tuple[list[dict], list[str]]:
    """Fetch completed/abandoned/parked experiments for a user.

    Returns (past_exp_records, past_titles) sorted most-recent-first by
    Ended At date. Used by both ``_build_memory_for_user`` and
    ``process_next_experiment_suggestion``.
    """
    user_rec = client.get_user(user_record_id)
    user_primary_id = _extract_fields(user_rec).get("User ID", "")

    past_exp_formula = (
        f"AND("
        f"FIND('{user_primary_id}', ARRAYJOIN({{User}})), "
        f"OR({{Status}} = 'completed', {{Status}} = 'abandoned', {{Status}} = 'parked')"
        f")"
    )
    past_exp_records = client.search_records("experiments", past_exp_formula, max_records=max_experiments)
    past_exp_records.sort(
        key=lambda x: _extract_fields(x).get(F_EXP_ENDED_AT) or "",
        reverse=True,
    )

    past_titles: list[str] = []
    if past_exp_records:
        past_titles = [
            _extract_fields(r).get(F_EXP_TITLE, "")
            for r in past_exp_records
            if _extract_fields(r).get(F_EXP_TITLE)
        ]

    return past_exp_records, past_titles


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
    - Uses coaching themes and executive summaries (not pattern scores) to
      ground experiment proposals.
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

    # 1. Fetch recent coaching data (themes, summaries, experiment progress)
    coaching_themes_by_run, executive_summaries_by_run, experiment_progress, eligible_runs = (
        _fetch_recent_coaching_data(client, user_record_id, max_runs=5)
    )

    if not eligible_runs:
        logger.info(
            "process_next_experiment_suggestion: no eligible runs for user %s — skipping",
            user_record_id,
        )
        return None

    # 2. Fetch past experiments and active experiment
    past_exp_records, past_titles = _fetch_experiment_history(client, user_record_id)

    # Fetch active experiment (if any) for progress section
    user_rec = client.get_user(user_record_id)
    user_primary_id = _extract_fields(user_rec).get("User ID", "")
    active_exp_formula = (
        f"AND("
        f"FIND('{user_primary_id}', ARRAYJOIN({{User}})), "
        f"{{Status}} = 'active'"
        f")"
    )
    active_exp_records = client.search_records("experiments", active_exp_formula, max_records=1)
    active_experiment = active_exp_records[0] if active_exp_records else None

    # 3. Build user message with coaching themes, executive summaries, and experiment context

    # ── COACHING THEME HISTORY ──
    theme_lines: list[str] = []
    for meeting_date, themes in coaching_themes_by_run:
        theme_lines.append(f"Meeting: {meeting_date}")
        for theme in themes:
            if isinstance(theme, dict):
                label = theme.get("label") or theme.get("theme") or "unknown"
                explanation = theme.get("explanation") or theme.get("detail") or ""
                priority = theme.get("priority", "")
                prefix = f"  {priority.capitalize()}: " if priority else "  Theme: "
                theme_lines.append(f'{prefix}"{label}" — {explanation}')
            elif isinstance(theme, str):
                theme_lines.append(f"  Theme: {theme}")
        theme_lines.append("")

    coaching_themes_section = ""
    if theme_lines:
        coaching_themes_section = (
            "── COACHING THEME HISTORY ──\n"
            "Recent coaching themes from this coachee's meeting analyses (most recent first):\n\n"
            + "\n".join(theme_lines)
        )

    # ── EXECUTIVE SUMMARIES ──
    exec_summary_lines: list[str] = []
    for meeting_date, summary in executive_summaries_by_run:
        exec_summary_lines.append(f'Meeting: {meeting_date}\n  "{summary}"\n')

    exec_summaries_section = ""
    if exec_summary_lines:
        exec_summaries_section = (
            "\n── EXECUTIVE SUMMARIES ──\n"
            "Recent executive summaries (most recent first, for progress context):\n\n"
            + "\n".join(exec_summary_lines)
        )

    # ── PAST EXPERIMENTS ──
    # Identify the most recently completed/parked experiment that needs a journey summary
    needs_summary_exp_record_id: Optional[str] = None
    needs_summary_exp_title: Optional[str] = None

    past_experiments_lines: list[str] = []
    for exp_rec in past_exp_records:
        ef = _extract_fields(exp_rec)
        exp_title = ef.get(F_EXP_TITLE, "unknown")
        exp_status = ef.get(F_EXP_STATUS, "")
        journey_summary = ef.get(F_EXP_JOURNEY_SUMMARY, "")
        related_patterns_raw = ef.get(F_EXP_RELATED_PATTERNS, "")
        pattern_id = ef.get(F_EXP_PATTERN_ID, "")

        # Parse related patterns
        related_patterns_list: list[str] = []
        if related_patterns_raw:
            try:
                related_patterns_list = json.loads(related_patterns_raw) if isinstance(related_patterns_raw, str) else related_patterns_raw
            except Exception:
                related_patterns_list = []

        # Get meeting count via experiment events
        try:
            _attempt_count, meeting_count = client.count_experiment_attempts_and_meetings(exp_rec["id"])
        except Exception:
            meeting_count = 0

        if journey_summary:
            past_experiments_lines.append(
                f'  Completed: "{exp_title}" ({meeting_count} meetings) — "{journey_summary}"'
            )
        else:
            # Legacy or needs summary
            patterns_display = ", ".join(related_patterns_list) if related_patterns_list else pattern_id or "none"
            past_experiments_lines.append(
                f'  Completed: "{exp_title}" ({meeting_count} meetings, related: [{patterns_display}])'
            )
            # Mark the most recent completed/parked experiment without a summary
            if needs_summary_exp_record_id is None and exp_status in ("completed", "parked"):
                needs_summary_exp_record_id = exp_rec["id"]
                needs_summary_exp_title = exp_title

    past_experiments_section = ""
    if past_experiments_lines:
        past_experiments_section = (
            "\n── PAST EXPERIMENTS ──\n"
            + "\n".join(past_experiments_lines)
        )

    # ── EXPERIMENT JOURNEY ──
    # Only if the most recently completed/parked experiment needs a journey summary
    experiment_journey_section = ""
    if needs_summary_exp_record_id and experiment_progress:
        journey_lines = [f'Just completed: "{needs_summary_exp_title}"']
        for meeting_date, attempt, count, coaching_note, *_ in experiment_progress:
            note_part = f' — "{coaching_note}"' if coaching_note else ""
            journey_lines.append(f"  Meeting {meeting_date}: {attempt} ({count} instances){note_part}")
        experiment_journey_section = (
            "\n── EXPERIMENT JOURNEY ──\n"
            + "\n".join(journey_lines)
        )

    # ── ACTIVE EXPERIMENT PROGRESS ──
    active_experiment_section = ""
    if active_experiment and experiment_progress:
        ae_fields = _extract_fields(active_experiment)
        ae_title = ae_fields.get(F_EXP_TITLE, "unknown")
        ae_instruction = ae_fields.get(F_EXP_INSTRUCTIONS, "") or ae_fields.get("Instruction", "")
        active_lines = [f'Active: "{ae_title}" — {ae_instruction}']
        for meeting_date, attempt, count, coaching_note, *_ in experiment_progress:
            note_part = f' — "{coaching_note}"' if coaching_note else ""
            active_lines.append(f"  Meeting {meeting_date}: {attempt} ({count} instances){note_part}")
        active_experiment_section = (
            "\n── ACTIVE EXPERIMENT PROGRESS ──\n"
            + "\n".join(active_lines)
        )

    # ── COACHING PRIORITY (pivot-park steering) ──
    coaching_priority_section = ""
    if eligible_runs:
        # Check the most recent run for a pivot-park graduation recommendation
        most_recent_run = eligible_runs[0]
        try:
            mr_parsed = json.loads(_extract_fields(most_recent_run).get(F_RUN_PARSED_JSON) or "{}")
            grad_rec = (mr_parsed.get("experiment_tracking") or {}).get("graduation_recommendation")
            if (
                isinstance(grad_rec, dict)
                and grad_rec.get("recommendation") == "park"
                and grad_rec.get("park_reason") == "pivot"
            ):
                pivot_rationale = grad_rec.get("rationale", "")
                if pivot_rationale:
                    coaching_priority_section = (
                        "\n── COACHING PRIORITY (from most recent analysis) ──\n"
                        "The coachee's previous experiment was parked because a more pressing priority emerged:\n"
                        f'"{pivot_rationale}"\n'
                        "Design your top-pick experiment to address this priority. The remaining options\n"
                        "should draw from the broader coaching history.\n"
                    )
        except Exception:
            pass

    # ── EXCLUDED TITLES ──
    avoid_titles_note = ""
    if past_titles:
        avoid_titles_note = (
            "\n── EXCLUDED TITLES ──\n"
            "Do NOT reuse any of these past experiment titles:\n"
            + "\n".join(f"  - {t}" for t in past_titles[:10])
        )

    # Request extra experiments as buffer in case some fail validation
    llm_request_count = max(num_to_generate + 2, num_to_generate)

    exp_word = "micro-experiment" if llm_request_count == 1 else "micro-experiments"
    user_message = (
        f"{coaching_themes_section}"
        f"{exec_summaries_section}"
        f"{past_experiments_section}"
        f"{experiment_journey_section}"
        f"{active_experiment_section}"
        f"{coaching_priority_section}"
        f"{avoid_titles_note}\n\n"
        f"── REQUEST ──\n"
        f"Propose exactly {llm_request_count} {exp_word} based on recurring coaching themes and behavioral gaps.\n"
        f"Ground each experiment in the coaching theme history above where available.\n\n"
        f"IMPORTANT: Return a JSON object with \"journey_summary\" (string or null) and \"experiments\" array "
        f"containing exactly {llm_request_count} experiment objects — no fewer."
    )

    # 5. Load system prompt from file and model name from active config
    experiment_system_prompt = load_next_experiment_system_prompt()

    logger.info(
        "process_next_experiment_suggestion: user=%s | sys_prompt=%d chars | "
        "user_message=%d chars | needs_journey_summary=%s",
        user_record_id,
        len(experiment_system_prompt),
        len(user_message),
        needs_summary_exp_record_id is not None,
    )

    model_name: Optional[str] = None
    try:
        active_cfg = client.get_active_config()
        if active_cfg:
            model_name = active_cfg.get("fields", {}).get("Model Name")
    except Exception:
        pass

    # 6-8. Call LLM, parse, and create experiments — retry if we get fewer than needed
    required_keys = {"experiment_id", "title", "instruction", "success_marker"}
    first_record_id: Optional[str] = None
    created_count = 0
    created_titles: set[str] = set()
    max_attempts = 2  # initial call + 1 retry

    for attempt in range(max_attempts):
        remaining = num_to_generate - created_count
        if remaining <= 0:
            break

        # On retry, request only the shortfall and add already-created titles to exclusions
        if attempt > 0:
            retry_request_count = max(remaining + 1, remaining)
            if retry_request_count <= 0:
                break
            extra_titles = "\n── EXCLUDED TITLES ──\n" \
                "Do NOT reuse any of these past experiment titles:\n" + \
                "\n".join(f"  - {t}" for t in list(past_titles[:10]) + list(created_titles))
            retry_exp_word = "micro-experiment" if retry_request_count == 1 else "micro-experiments"
            current_user_message = (
                f"{coaching_themes_section}"
                f"{exec_summaries_section}"
                f"{past_experiments_section}"
                f"{experiment_journey_section}"
                f"{active_experiment_section}"
                f"{extra_titles}\n\n"
                f"── REQUEST ──\n"
                f"Propose exactly {retry_request_count} {retry_exp_word} based on recurring coaching themes and behavioral gaps.\n"
                f"Ground each experiment in the coaching theme history above where available.\n\n"
                f"IMPORTANT: Return a JSON object with \"journey_summary\" (string or null) and \"experiments\" array "
                f"containing exactly {retry_request_count} experiment objects — no fewer."
            )
            current_max_tokens = 600 * retry_request_count + 300  # extra for journey_summary
            logger.info(
                "process_next_experiment_suggestion: retry attempt %d — requesting %d more experiments for user %s",
                attempt, retry_request_count, user_record_id,
            )
        else:
            current_user_message = user_message
            current_max_tokens = 600 * llm_request_count + 300  # extra for journey_summary

        # 6. Call LLM
        try:
            openai_resp = call_llm(
                system_prompt=experiment_system_prompt,
                developer_message="",
                user_message=current_user_message,
                model=model_name,
                max_tokens=current_max_tokens,
            )
        except Exception as exc:
            logger.error("process_next_experiment_suggestion: OpenAI call failed (attempt %d): %s", attempt, exc)
            if attempt == 0:
                return None
            break

        # 7. Parse response — strip accidental markdown fences
        raw = openai_resp.raw_text.strip()
        logger.info(
            "process_next_experiment_suggestion: raw LLM response attempt %d (first 1500 chars): %.1500s",
            attempt, raw,
        )
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
                "process_next_experiment_suggestion: JSON parse failed (attempt %d): %s | raw: %.500s",
                attempt, exc, raw,
            )
            if attempt == 0:
                return None
            break

        # Extract journey_summary and experiments list from response
        journey_summary: Optional[str] = None
        if isinstance(parsed_response, dict):
            journey_summary = parsed_response.get("journey_summary")
            experiments_list = parsed_response.get("experiments", [])
        else:
            # Fallback: if LLM returns an array, treat as experiments with no summary
            experiments_list = parsed_response if isinstance(parsed_response, list) else []
            journey_summary = None

        if not isinstance(experiments_list, list):
            logger.error("process_next_experiment_suggestion: unexpected experiments type: %s", type(experiments_list))
            if attempt == 0:
                return None
            break

        logger.info(
            "process_next_experiment_suggestion: LLM returned %d experiments (attempt %d) for user %s, journey_summary=%s",
            len(experiments_list), attempt, user_record_id,
            "present" if journey_summary else "absent",
        )

        # Store journey summary on the experiment that needs it (first successful attempt only)
        if journey_summary and needs_summary_exp_record_id and attempt == 0:
            try:
                client.update_record("experiments", needs_summary_exp_record_id, {
                    F_EXP_JOURNEY_SUMMARY: journey_summary
                })
                logger.info("Stored journey summary for experiment %s", needs_summary_exp_record_id)
            except Exception as exc:
                logger.warning("Failed to store journey summary: %s", exc)

        # 8. Validate and create experiment records
        for micro in experiments_list:
            if created_count >= num_to_generate:
                break
            # Normalise common LLM key-name variations
            if "instructions" in micro and "instruction" not in micro:
                micro["instruction"] = micro.pop("instructions")
            missing = required_keys - micro.keys()
            if missing:
                logger.warning("process_next_experiment_suggestion: skipping proposal with missing fields %s", missing)
                continue
            # Reject placeholder / refusal responses
            instr_text = micro.get("instruction", "")
            if len(instr_text) < 40 or micro.get("success_marker", "") == "N/A":
                logger.warning(
                    "process_next_experiment_suggestion: skipping placeholder experiment (instruction=%d chars, success_marker=%s)",
                    len(instr_text), micro.get("success_marker", "")[:30],
                )
                continue
            # Deduplicate against past titles
            proposed_title = micro.get("title", "")
            title_lower = proposed_title.strip().lower()
            if title_lower in {t.strip().lower() for t in past_titles}:
                logger.warning(
                    "process_next_experiment_suggestion: skipping duplicate title '%s'",
                    proposed_title[:80],
                )
                continue
            if title_lower in {t.strip().lower() for t in created_titles}:
                logger.warning(
                    "process_next_experiment_suggestion: skipping already-created title '%s'",
                    proposed_title[:80],
                )
                continue

            # related_patterns is optional — default to empty list
            related_patterns = micro.get("related_patterns", [])
            if not isinstance(related_patterns, list):
                related_patterns = []

            created_titles.add(proposed_title)

            # 9. Create proposed experiment record
            exp_fields: dict = {
                F_EXP_TITLE: micro["title"][:140],
                F_EXP_INSTRUCTIONS: micro["instruction"][:600],
                F_EXP_SUCCESS_CRITERIA: micro["success_marker"][:300],
                F_EXP_SUCCESS_MARKER: micro["success_marker"][:300],
                F_EXP_RELATED_PATTERNS: json.dumps(related_patterns),
                F_EXP_PATTERN_ID: "",  # Deprecated — leave empty for new experiments
                F_EXP_STATUS: "proposed",
                F_EXP_USER: [user_record_id],
            }

            exp_record = client.create_experiment(exp_fields)
            exp_record_id = exp_record["id"]
            created_count += 1

            if first_record_id is None:
                first_record_id = exp_record_id

            logger.info(
                "process_next_experiment_suggestion: proposed experiment %s for user %s (related_patterns: %s)",
                exp_record_id, user_record_id, related_patterns,
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
    """Build the memory block for a single_meeting prompt.

    Includes baseline profile, active experiment, coaching history from
    recent meetings, and experiment history (completed/parked/abandoned).
    """
    if not user_record_id:
        return MemoryBlock()

    user_rec = client.get_user(user_record_id)
    user_fields = _extract_fields(user_rec)

    # Check for active baseline pack
    bp_links = _get_link_ids(user_fields, "Active Baseline Pack")
    baseline_pack_id_str = None

    if bp_links:
        bp_rec = client.get_baseline_pack(bp_links[0])
        bp_fields = _extract_fields(bp_rec)
        baseline_pack_id_str = bp_fields.get("Baseline Pack ID")

    # Active experiment
    active_exp_data: Optional[dict] = None
    if active_exp_record_id:
        exp_rec = client.get_experiment(active_exp_record_id)
        exp_fields = _extract_fields(exp_rec)
        # Parse related_patterns from Airtable (JSON string); fall back to
        # wrapping legacy Pattern ID if Related Patterns is empty.
        related_patterns_raw = exp_fields.get("Related Patterns") or ""
        related_patterns: list[str] = []
        if related_patterns_raw:
            try:
                related_patterns = json.loads(related_patterns_raw)
            except (json.JSONDecodeError, TypeError):
                related_patterns = []
        if not related_patterns:
            legacy_pid = exp_fields.get("Pattern ID")
            if legacy_pid:
                related_patterns = [legacy_pid]
        active_exp_data = {
            "experiment_id": exp_fields.get("Experiment ID"),
            "title": exp_fields.get("Title"),
            "instruction": exp_fields.get("Instruction") or exp_fields.get("Instructions"),
            "success_marker": exp_fields.get("Success Marker") or exp_fields.get("Success Criteria"),
            "related_patterns": related_patterns,
            "pattern_id": exp_fields.get("Pattern ID"),  # Backward compat
            "status": exp_fields.get("Status"),
        }

    # Coaching history: recent meeting themes + executive summaries
    coaching_history: list[dict] = []
    try:
        themes_by_run, summaries_by_run, experiment_progress_tuples, _ = _fetch_recent_coaching_data(
            client, user_record_id, max_runs=MAX_COACHING_HISTORY_MEETINGS,
        )
        # Build one entry per meeting, keyed by date. Merge themes and
        # summaries since they come from the same runs but are extracted
        # into separate lists.
        summaries_map = dict(summaries_by_run)
        dates_seen: set[str] = set()
        for meeting_date, themes in themes_by_run:
            if meeting_date in dates_seen:
                continue
            dates_seen.add(meeting_date)
            coaching_history.append({
                "meeting_date": meeting_date,
                "executive_summary": summaries_map.get(meeting_date, ""),
                "coaching_themes": themes,
            })
        # Add any meetings that had an executive summary but no themes
        for meeting_date, summary in summaries_by_run:
            if meeting_date not in dates_seen:
                dates_seen.add(meeting_date)
                coaching_history.append({
                    "meeting_date": meeting_date,
                    "executive_summary": summary,
                    "coaching_themes": [],
                })
    except Exception as exc:
        logger.warning("Failed to fetch coaching history: %s", exc)

    # Experiment progress: per-meeting attempt history for the active experiment.
    # Filter to only include attempts for the CURRENT active experiment to prevent
    # cross-contamination from prior experiments.
    active_exp_id = active_exp_data.get("experiment_id") if active_exp_data else None
    experiment_progress: list[dict] = [
        {
            "meeting_date": meeting_date,
            "attempt": attempt,
            "count_attempts": count,
            "coaching_note": note,
        }
        for meeting_date, attempt, count, note, det_exp_id in experiment_progress_tuples
        if not active_exp_id or det_exp_id == active_exp_id
    ]

    # Experiment history: completed/parked/abandoned experiments
    experiment_history: list[dict] = []
    try:
        past_exp_records, _ = _fetch_experiment_history(client, user_record_id)
        for exp_rec in past_exp_records[:MAX_EXPERIMENT_HISTORY]:
            ef = _extract_fields(exp_rec)
            related_raw = ef.get(F_EXP_RELATED_PATTERNS, "")
            related_list: list[str] = []
            if related_raw:
                try:
                    related_list = json.loads(related_raw) if isinstance(related_raw, str) else related_raw
                except Exception:
                    related_list = []
            experiment_history.append({
                "title": ef.get(F_EXP_TITLE, "unknown"),
                "status": ef.get(F_EXP_STATUS, "unknown"),
                "related_patterns": related_list,
                "journey_summary": ef.get(F_EXP_JOURNEY_SUMMARY, ""),
            })
    except Exception as exc:
        logger.warning("Failed to fetch experiment history: %s", exc)

    return build_memory_block(
        baseline_pack_id=baseline_pack_id_str,
        active_experiment=active_exp_data,
        coaching_history=coaching_history,
        experiment_history=experiment_history,
        experiment_progress=experiment_progress,
    )


def _load_developer_message_from_config(client: AirtableClient, config_links: list[str]) -> str:
    """Load taxonomy developer message from canonical file, with Airtable fallback.

    Prefers the file-based version (single source of truth). If the Airtable
    "Taxonomy Compact Block" is also populated and differs, logs a drift warning.
    Falls back to Airtable only if the canonical file is unavailable.
    """
    # Try canonical file first
    file_based = ""
    try:
        from .prompt_builder import build_developer_message
        file_based = build_developer_message()
    except Exception as exc:
        logger.warning("Failed to load taxonomy from canonical file: %s", exc)

    # Load Airtable version for drift check / fallback
    airtable_based = ""
    if config_links:
        try:
            cfg = client.get_record("config", config_links[0])
            airtable_based = _extract_fields(cfg).get("Taxonomy Compact Block", "")
        except Exception:
            pass
    if not airtable_based:
        try:
            cfg = client.get_active_config()
            if cfg:
                airtable_based = cfg.get("fields", {}).get("Taxonomy Compact Block", "")
        except Exception:
            pass

    if file_based:
        if airtable_based and airtable_based.strip() != file_based.strip():
            logger.warning(
                "Taxonomy drift detected: Airtable 'Taxonomy Compact Block' differs "
                "from canonical file. Using file-based version."
            )
        return file_based

    # Fallback to Airtable if file is missing/empty
    if airtable_based:
        logger.warning("Canonical taxonomy file unavailable; falling back to Airtable.")
        return airtable_based

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