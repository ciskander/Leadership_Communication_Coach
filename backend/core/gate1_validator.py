"""
gate1_validator.py — Strict JSON schema + business rule validation for OpenAI output.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

from .config import MVP_SCHEMA_PATH, PATTERN_ORDER
from .models import Gate1Result, ValidationIssue

logger = logging.getLogger(__name__)

# ── Load schema once at import time ──────────────────────────────────────────

def _load_schema() -> dict:
    with open(MVP_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_SCHEMA: dict = _load_schema()
_VALIDATOR = Draft202012Validator(_SCHEMA)

# ── ID format regexes ─────────────────────────────────────────────────────────
_ID_PATTERNS = {
    "analysis_id": re.compile(r"^A-\d{6}$"),
    "meeting_id": re.compile(r"^M-\d{6}$"),
    "baseline_pack_id": re.compile(r"^BP-\d{6}$"),
    "experiment_id": re.compile(r"^EXP-\d{6}$"),
    "evidence_span_id": re.compile(r"^ES-\d{3}$"),
}

_PATTERN_ID_ENUM = set(PATTERN_ORDER)

_NUMERIC_PATTERNS = set(PATTERN_ORDER) - {"conversational_balance"}


def _issue(severity: str, code: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity=severity, issue_code=code, path=path, message=message)


def _err(code: str, path: str, message: str) -> ValidationIssue:
    return _issue("error", code, path, message)


def _warn(code: str, path: str, message: str) -> ValidationIssue:
    return _issue("warning", code, path, message)


# ── Public entry point ────────────────────────────────────────────────────────

def validate(raw_text: str) -> Gate1Result:
    """
    Run the full Gate1 validation pipeline.

    Steps:
        1. JSON parse
        2. JSON Schema validation
        3. Business rules

    Returns:
        Gate1Result with passed flag and list of issues.
    """
    issues: list[ValidationIssue] = []

    # ── Step 1: JSON parse ────────────────────────────────────────────────────
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        issues.append(_err("JSON_PARSE_ERROR", "$", f"JSON parse failed: {exc}"))
        return Gate1Result(passed=False, issues=issues)

    # ── Step 2: JSON Schema ───────────────────────────────────────────────────
    schema_errors = list(_VALIDATOR.iter_errors(data))
    for error in schema_errors:
        path = ".".join(str(p) for p in error.absolute_path) or "$"
        issues.append(_err("SCHEMA_VIOLATION", path, error.message))

    if issues:
        # Schema errors are fatal; skip business rules for cleaner reporting
        return Gate1Result(passed=False, issues=issues)

    # ── Step 3: Business rules ────────────────────────────────────────────────
    issues.extend(_business_rules(data))

    passed = all(i.severity != "error" for i in issues)
    return Gate1Result(passed=passed, issues=issues)


def _business_rules(data: dict) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    analysis_type = data.get("meta", {}).get("analysis_type", "")
    pattern_snapshot = data.get("pattern_snapshot", [])
    evidence_spans = data.get("evidence_spans", [])
    coaching_output = data.get("coaching_output", {})
    experiment_tracking = data.get("experiment_tracking", {})

    # Build valid evidence span ID set
    valid_es_ids = {span.get("evidence_span_id") for span in evidence_spans}

    # ── 3a. pattern_snapshot must have exactly 10 items in required order ─────
    if len(pattern_snapshot) != 10:
        issues.append(_err(
            "PATTERN_SNAPSHOT_COUNT",
            "pattern_snapshot",
            f"Expected 10 items, got {len(pattern_snapshot)}.",
        ))
    else:
        for idx, (item, expected_id) in enumerate(zip(pattern_snapshot, PATTERN_ORDER)):
            pid = item.get("pattern_id")
            if pid != expected_id:
                issues.append(_err(
                    "PATTERN_ORDER",
                    f"pattern_snapshot[{idx}].pattern_id",
                    f"Expected '{expected_id}', got '{pid}'.",
                ))

    # ── 3b. evaluation_summary arrays partition all 10 pattern_ids ────────────
    eval_summary = data.get("evaluation_summary", {})
    all_reported: list[str] = (
        eval_summary.get("patterns_evaluated", [])
        + eval_summary.get("patterns_insufficient_signal", [])
        + eval_summary.get("patterns_not_evaluable", [])
    )
    reported_set = set(all_reported)
    if reported_set != _PATTERN_ID_ENUM:
        missing = _PATTERN_ID_ENUM - reported_set
        extra = reported_set - _PATTERN_ID_ENUM
        if missing:
            issues.append(_err(
                "EVAL_SUMMARY_MISSING",
                "evaluation_summary",
                f"Missing pattern IDs: {sorted(missing)}",
            ))
        if extra:
            issues.append(_err(
                "EVAL_SUMMARY_EXTRA",
                "evaluation_summary",
                f"Unknown pattern IDs: {sorted(extra)}",
            ))
    if len(all_reported) != len(set(all_reported)):
        issues.append(_err(
            "EVAL_SUMMARY_DUPLICATE",
            "evaluation_summary",
            "Duplicate pattern IDs across evaluation_summary arrays.",
        ))

    # ── 3c. Pattern snapshot item validation ──────────────────────────────────
    for idx, item in enumerate(pattern_snapshot):
        pid = item.get("pattern_id", "")
        path = f"pattern_snapshot[{idx}]"
        status = item.get("evaluable_status")

        if status == "evaluable":
            if pid == "conversational_balance":
                # Must have balance_assessment, must NOT have num/denom/ratio
                if not item.get("balance_assessment"):
                    issues.append(_err(
                        "CONV_BALANCE_MISSING_ASSESSMENT",
                        f"{path}.balance_assessment",
                        "conversational_balance evaluable item must have balance_assessment.",
                    ))
                for forbidden in ("numerator", "denominator", "ratio"):
                    if item.get(forbidden) is not None:
                        issues.append(_err(
                            "CONV_BALANCE_FORBIDDEN_FIELD",
                            f"{path}.{forbidden}",
                            f"conversational_balance must not have {forbidden}.",
                        ))
            else:
                # Numeric evaluable: must have num/denom/ratio
                num = item.get("numerator")
                den = item.get("denominator")
                ratio = item.get("ratio")
                if den is None or den < 1:
                    issues.append(_err(
                        "INVALID_DENOMINATOR",
                        f"{path}.denominator",
                        "Evaluable numeric pattern must have denominator >= 1.",
                    ))
                elif num is not None:
                    if num < 0:
                        issues.append(_err(
                            "INVALID_NUMERATOR",
                            f"{path}.numerator",
                            "numerator must be >= 0.",
                        ))
                    if num > den:
                        issues.append(_err(
                            "NUMERATOR_EXCEEDS_DENOMINATOR",
                            f"{path}",
                            f"numerator ({num}) > denominator ({den}).",
                        ))
                    if ratio is not None and not (0 <= ratio <= 1):
                        issues.append(_err(
                            "RATIO_OUT_OF_RANGE",
                            f"{path}.ratio",
                            f"ratio ({ratio}) must be in [0, 1].",
                        ))
        elif status in ("insufficient_signal", "not_evaluable"):
            for forbidden in ("numerator", "denominator", "ratio"):
                if item.get(forbidden) is not None:
                    issues.append(_err(
                        "NON_EVALUABLE_HAS_NUMERIC",
                        f"{path}.{forbidden}",
                        f"{status} item must not have {forbidden}.",
                    ))

        # evidence_span_ids reference check
        for es_id in item.get("evidence_span_ids", []):
            if not _ID_PATTERNS["evidence_span_id"].match(str(es_id)):
                issues.append(_err(
                    "INVALID_ES_ID_FORMAT",
                    f"{path}.evidence_span_ids",
                    f"Invalid evidence_span_id format: {es_id}",
                ))
            elif es_id not in valid_es_ids:
                issues.append(_err(
                    "DANGLING_ES_REFERENCE",
                    f"{path}.evidence_span_ids",
                    f"evidence_span_id {es_id} not found in evidence_spans.",
                ))

        # 2-layer scoring trace consistency (if present)
        opp_events = item.get("opportunity_events")
        if opp_events is not None:
            if pid == "conversational_balance" or status != "evaluable":
                issues.append(_err(
                    "OPP_EVENTS_FORBIDDEN",
                    f"{path}.opportunity_events",
                    "opportunity_events only allowed on numeric evaluable patterns.",
                ))
            else:
                considered = item.get("opportunity_events_considered")
                counted = item.get("opportunity_events_counted")
                den = item.get("denominator")
                num = item.get("numerator")
                if considered != len(opp_events):
                    issues.append(_err(
                        "OPP_EVENTS_COUNT_MISMATCH",
                        f"{path}.opportunity_events_considered",
                        f"opportunity_events_considered ({considered}) != len(opportunity_events) ({len(opp_events)}).",
                    ))
                counted_actual = sum(
                    1 for e in opp_events if e.get("count_decision") == "counted"
                )
                if counted != counted_actual:
                    issues.append(_err(
                        "OPP_EVENTS_COUNTED_MISMATCH",
                        f"{path}.opportunity_events_counted",
                        f"opportunity_events_counted ({counted}) != actual counted events ({counted_actual}).",
                    ))
                if den is not None and counted is not None and den != counted:
                    issues.append(_err(
                        "DENOMINATOR_COUNTED_MISMATCH",
                        f"{path}.denominator",
                        f"denominator ({den}) must equal opportunity_events_counted ({counted}).",
                    ))
                yes_counted = sum(
                    1 for e in opp_events
                    if e.get("count_decision") == "counted" and e.get("success") == "yes"
                )
                if num is not None and num != yes_counted:
                    issues.append(_err(
                        "NUMERATOR_YES_MISMATCH",
                        f"{path}.numerator",
                        f"numerator ({num}) must equal count(counted AND success=yes) ({yes_counted}).",
                    ))

    # ── 3d. turn_start_id / turn_end_id in evidence_spans ────────────────────
    for idx, span in enumerate(evidence_spans):
        path = f"evidence_spans[{idx}]"
        for field in ("turn_start_id", "turn_end_id"):
            val = span.get(field)
            if val is not None:
                if not isinstance(val, int) or val < 1:
                    issues.append(_err(
                        "INVALID_TURN_ID",
                        f"{path}.{field}",
                        f"{field} must be an integer >= 1, got {val!r}.",
                    ))

    # ── 3e. coaching_output cardinality ──────────────────────────────────────
    strengths = coaching_output.get("strengths", [])
    focus = coaching_output.get("focus", [])
    micro_experiment = coaching_output.get("micro_experiment", [])

    if not (0 <= len(strengths) <= 2):
        issues.append(_err(
            "COACHING_STRENGTHS_COUNT",
            "coaching_output.strengths",
            f"strengths must have 0-2 items, got {len(strengths)}.",
        ))
    if len(focus) != 1:
        issues.append(_err(
            "COACHING_FOCUS_COUNT",
            "coaching_output.focus",
            f"focus must have exactly 1 item, got {len(focus)}.",
        ))
    if len(micro_experiment) != 1:
        issues.append(_err(
            "COACHING_MICRO_EXP_COUNT",
            "coaching_output.micro_experiment",
            f"micro_experiment must have exactly 1 item, got {len(micro_experiment)}.",
        ))

    # evidence_span_ids must be non-empty and valid for coaching items
    for key, items in [("strengths", strengths), ("focus", focus), ("micro_experiment", micro_experiment)]:
        for i, item in enumerate(items):
            es_ids = item.get("evidence_span_ids", [])
            if not es_ids:
                issues.append(_err(
                    "COACHING_EMPTY_ES_IDS",
                    f"coaching_output.{key}[{i}].evidence_span_ids",
                    "evidence_span_ids must be non-empty in coaching_output items.",
                ))
            for es_id in es_ids:
                if es_id not in valid_es_ids:
                    issues.append(_err(
                        "COACHING_DANGLING_ES",
                        f"coaching_output.{key}[{i}].evidence_span_ids",
                        f"evidence_span_id {es_id} not found in evidence_spans.",
                    ))

    # ── 3f. Experiment tracking conditional rules ─────────────────────────────
    active_exp = experiment_tracking.get("active_experiment", {}) or {}
    detection = experiment_tracking.get("detection_in_this_meeting")
    status = active_exp.get("status", "none")

    if analysis_type == "baseline_pack":
        if detection is not None:
            issues.append(_err(
                "BP_DETECTION_MUST_BE_NULL",
                "experiment_tracking.detection_in_this_meeting",
                "baseline_pack analysis must have detection_in_this_meeting = null.",
            ))
    elif analysis_type == "single_meeting":
        if status in ("assigned", "active"):
            if detection is None:
                issues.append(_err(
                    "SINGLE_MEETING_DETECTION_REQUIRED",
                    "experiment_tracking.detection_in_this_meeting",
                    "active/assigned experiment requires detection_in_this_meeting to be non-null.",
                ))
            elif detection is not None:
                # If attempt detected, evidence_span_ids must be non-empty
                attempt = detection.get("attempt")
                if attempt in ("partial", "yes"):
                    es_ids = detection.get("evidence_span_ids", [])
                    if not es_ids:
                        issues.append(_err(
                            "DETECTION_ATTEMPT_NO_EVIDENCE",
                            "experiment_tracking.detection_in_this_meeting.evidence_span_ids",
                            "attempt_detected requires non-empty evidence_span_ids.",
                        ))
        elif status in ("none", "completed", "abandoned") or status is None:
            if detection is not None:
                issues.append(_warn(
                    "DETECTION_UNEXPECTED",
                    "experiment_tracking.detection_in_this_meeting",
                    "detection_in_this_meeting should be null when no active experiment.",
                ))

    # ── 3g. ID format validation ──────────────────────────────────────────────
    _check_id_format(data, "meta.analysis_id", data.get("meta", {}).get("analysis_id"), "analysis_id", issues)

    ctx = data.get("context", {})
    if "meeting_id" in ctx:
        _check_id_format(data, "context.meeting_id", ctx["meeting_id"], "meeting_id", issues)
    if "baseline_pack_id" in ctx:
        _check_id_format(data, "context.baseline_pack_id", ctx["baseline_pack_id"], "baseline_pack_id", issues)

    if micro_experiment:
        exp_id = micro_experiment[0].get("experiment_id")
        _check_id_format(data, "coaching_output.micro_experiment[0].experiment_id", exp_id, "experiment_id", issues)

    return issues


def _check_id_format(
    _data: dict,
    path: str,
    value: Any,
    id_type: str,
    issues: list[ValidationIssue],
) -> None:
    if value is None:
        return
    pattern = _ID_PATTERNS.get(id_type)
    if pattern and not pattern.match(str(value)):
        issues.append(_err(
            "INVALID_ID_FORMAT",
            path,
            f"'{value}' does not match expected format for {id_type}.",
        ))
