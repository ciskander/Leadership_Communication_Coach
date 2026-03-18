"""
gate1_validator.py — Strict JSON schema + business rule validation for OpenAI output.

Includes a lightweight sanitisation pass that corrects known LLM enum
confusions *before* schema validation so that minor hallucinated enum values
do not cause otherwise-valid output to fail Gate1.
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


# ── Pre-validation sanitiser ─────────────────────────────────────────────────

_VALID_TARGET_CONTROL = {"yes", "no", "unclear"}
_VALID_COUNT_DECISION = {"counted", "excluded"}
_VALID_SUCCESS = {"yes", "no", "na"}


def _build_allowed_keys_map(schema: dict) -> dict[str, set[str]]:
    """Extract allowed property names for each schema definition that has additionalProperties=false.

    Returns a mapping from definition name → set of allowed property keys.
    Also includes "ROOT" for the top-level schema.
    """
    defs = schema.get("$defs", schema.get("definitions", {}))
    allowed: dict[str, set[str]] = {}
    for name, defn in defs.items():
        if defn.get("additionalProperties") is False and "properties" in defn:
            allowed[name] = set(defn["properties"].keys())
    if schema.get("additionalProperties") is False and "properties" in schema:
        allowed["ROOT"] = set(schema["properties"].keys())
    return allowed


_ALLOWED_KEYS = _build_allowed_keys_map(_SCHEMA)


def _best_match(key: str, allowed: set[str], max_distance: int = 5) -> str | None:
    """Find the best fuzzy match for an unrecognized key among allowed keys.

    Uses Levenshtein edit distance. Returns the closest allowed key if the
    distance is within max_distance, otherwise None. Ties are broken by
    shorter distance; among ties, alphabetical order.
    """
    from difflib import SequenceMatcher

    key_lower = key.lower()
    best: tuple[float, str] | None = None  # (similarity_ratio, candidate)
    for candidate in allowed:
        ratio = SequenceMatcher(None, key_lower, candidate.lower()).ratio()
        if best is None or ratio > best[0]:
            best = (ratio, candidate)
    # Require at least 60% similarity
    if best and best[0] >= 0.6:
        return best[1]
    return None


def _fix_extra_keys(obj: dict, allowed: set[str], path: str) -> int:
    """Rename or remove keys not in the allowed set.  Returns count of fixes.

    If an unrecognized key closely matches an allowed key that isn't already
    present, the value is moved to the correct key name (preserving data).
    Otherwise, the key is stripped.
    """
    extra = set(obj.keys()) - allowed
    fixes = 0
    for key in extra:
        match = _best_match(key, allowed)
        if match and match not in obj:
            logger.warning(
                "Sanitiser: renaming unrecognized key %r → %r at %s",
                key, match, path,
            )
            obj[match] = obj.pop(key)
        else:
            logger.warning("Sanitiser: stripping unrecognized key %r at %s", key, path)
            del obj[key]
        fixes += 1
    return fixes


def _sanitise_output(data: dict) -> int:
    """
    Correct known LLM output issues in-place.  Returns the number of fixes applied.

    1. Strip unrecognized keys from every object (prevents additionalProperties
       validation failures from hallucinated field names).
    2. Fix known LLM enum confusions in opportunity_events.
    """
    fixes = 0

    # ── Strip unrecognized keys from all schema-controlled objects ────────
    fixes += _fix_extra_keys(data, _ALLOWED_KEYS.get("ROOT", set()), "$")

    if "meta" in data and isinstance(data["meta"], dict):
        fixes += _fix_extra_keys(data["meta"], _ALLOWED_KEYS.get("Meta", set()), "$.meta")

    if "context" in data and isinstance(data["context"], dict):
        # Determine which context schema applies
        ctx_keys = _ALLOWED_KEYS.get("SingleMeetingContext", set()) | _ALLOWED_KEYS.get("BaselinePackContext", set())
        fixes += _fix_extra_keys(data["context"], ctx_keys, "$.context")

    if "evaluation_summary" in data and isinstance(data["evaluation_summary"], dict):
        fixes += _fix_extra_keys(data["evaluation_summary"], _ALLOWED_KEYS.get("EvaluationSummary", set()), "$.evaluation_summary")

    if "coaching_output" in data and isinstance(data["coaching_output"], dict):
        co = data["coaching_output"]
        fixes += _fix_extra_keys(co, _ALLOWED_KEYS.get("CoachingOutput", set()), "$.coaching_output")
        ci_keys = _ALLOWED_KEYS.get("CoachingItem", set())
        for i, s in enumerate(co.get("strengths", [])):
            if isinstance(s, dict):
                fixes += _fix_extra_keys(s, ci_keys, f"$.coaching_output.strengths[{i}]")
        for i, f in enumerate(co.get("focus", [])):
            if isinstance(f, dict):
                fixes += _fix_extra_keys(f, ci_keys, f"$.coaching_output.focus[{i}]")
        me_keys = _ALLOWED_KEYS.get("MicroExperiment", set())
        for i, m in enumerate(co.get("micro_experiment", [])):
            if isinstance(m, dict):
                fixes += _fix_extra_keys(m, me_keys, f"$.coaching_output.micro_experiment[{i}]")

    ps_keys = _ALLOWED_KEYS.get("PatternMeasurementBase", set())
    oe_keys = _ALLOWED_KEYS.get("OpportunityEvent", set())
    for i, item in enumerate(data.get("pattern_snapshot", [])):
        if isinstance(item, dict):
            fixes += _fix_extra_keys(item, ps_keys, f"$.pattern_snapshot[{i}]")
            for j, event in enumerate(item.get("opportunity_events", []) or []):
                if isinstance(event, dict):
                    fixes += _fix_extra_keys(event, oe_keys, f"$.pattern_snapshot[{i}].opportunity_events[{j}]")

    es_keys = _ALLOWED_KEYS.get("EvidenceSpan", set())
    for i, span in enumerate(data.get("evidence_spans", [])):
        if isinstance(span, dict):
            fixes += _fix_extra_keys(span, es_keys, f"$.evidence_spans[{i}]")

    if "experiment_tracking" in data and isinstance(data["experiment_tracking"], dict):
        et = data["experiment_tracking"]
        fixes += _fix_extra_keys(et, _ALLOWED_KEYS.get("ExperimentTracking", set()), "$.experiment_tracking")
        ae = et.get("active_experiment")
        if isinstance(ae, dict):
            fixes += _fix_extra_keys(ae, _ALLOWED_KEYS.get("ActiveExperiment", set()), "$.experiment_tracking.active_experiment")
        det = et.get("detection_in_this_meeting")
        if isinstance(det, dict):
            fixes += _fix_extra_keys(det, _ALLOWED_KEYS.get("ExperimentDetection", set()), "$.experiment_tracking.detection_in_this_meeting")

    # ── Normalise experiment_id format ─────────────────────────────────────
    # The LLM sometimes generates IDs like "EXP-260316-01" instead of the
    # required "EXP-NNNNNN" format.  Extract digits and zero-pad to 6.
    _exp_id_re = _ID_PATTERNS["experiment_id"]
    def _fix_exp_id(obj: dict, field: str, path: str) -> int:
        val = obj.get(field)
        if val and isinstance(val, str) and not _exp_id_re.match(val):
            digits = re.sub(r"[^0-9]", "", val)
            if digits:
                normalised = f"EXP-{digits[:6].zfill(6)}"
                logger.warning("Sanitiser: experiment_id %r → %r at %s", val, normalised, path)
                obj[field] = normalised
                return 1
        return 0

    # micro_experiment items
    for i, m in enumerate((data.get("coaching_output") or {}).get("micro_experiment", [])):
        if isinstance(m, dict):
            fixes += _fix_exp_id(m, "experiment_id", f"$.coaching_output.micro_experiment[{i}].experiment_id")

    # experiment_tracking.active_experiment
    ae = (data.get("experiment_tracking") or {}).get("active_experiment")
    if isinstance(ae, dict):
        fixes += _fix_exp_id(ae, "experiment_id", "$.experiment_tracking.active_experiment.experiment_id")

    # experiment_tracking.detection_in_this_meeting
    det = (data.get("experiment_tracking") or {}).get("detection_in_this_meeting")
    if isinstance(det, dict):
        fixes += _fix_exp_id(det, "experiment_id", "$.experiment_tracking.detection_in_this_meeting.experiment_id")

    # ── Fix known LLM enum confusions in opportunity_events ──────────────
    for item in data.get("pattern_snapshot", []):
        for event in item.get("opportunity_events", []) or []:
            tc = event.get("target_control")
            if tc is not None and tc not in _VALID_TARGET_CONTROL:
                inferred = "yes" if tc == "counted" else "no" if tc == "excluded" else "unclear"
                logger.warning(
                    "Sanitiser: target_control %r → %r (event %s)",
                    tc, inferred, event.get("event_id"),
                )
                event["target_control"] = inferred
                fixes += 1

            cd = event.get("count_decision")
            if cd is not None and cd not in _VALID_COUNT_DECISION:
                inferred = "counted" if cd in ("yes",) else "excluded"
                logger.warning(
                    "Sanitiser: count_decision %r → %r (event %s)",
                    cd, inferred, event.get("event_id"),
                )
                event["count_decision"] = inferred
                fixes += 1

            su = event.get("success")
            if su is not None and su not in _VALID_SUCCESS:
                inferred = "yes" if su == "counted" else "no" if su == "excluded" else "na"
                logger.warning(
                    "Sanitiser: success %r → %r (event %s)",
                    su, inferred, event.get("event_id"),
                )
                event["success"] = inferred
                fixes += 1

    if fixes:
        logger.info("Sanitiser applied %d fix(es) total.", fixes)
    return fixes


# ── Public entry point ────────────────────────────────────────────────────────

def validate(raw_text: str) -> Gate1Result:
    """
    Run the full Gate1 validation pipeline.

    Steps:
        1. JSON parse
        1b. Sanitise known LLM enum confusions
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

    # ── Step 1b: Sanitise known LLM output quirks ─────────────────────────────
    _sanitise_output(data)

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
                # Numeric evaluable: must have num/denom/ratio.
                # Exception: median_of_meeting_level_ratios (baseline pack aggregate)
                # produces null numerator/denominator with a valid ratio — this is expected.
                num = item.get("numerator")
                den = item.get("denominator")
                ratio = item.get("ratio")
                is_median = item.get("denominator_rule_id") == "median_of_meeting_level_ratios"
                if is_median:
                    if ratio is None:
                        issues.append(_err(
                            "MEDIAN_PATTERN_MISSING_RATIO",
                            f"{path}.ratio",
                            "median_of_meeting_level_ratios pattern must have a ratio value.",
                        ))
                    elif not (0 <= ratio <= 1):
                        issues.append(_err(
                            "RATIO_OUT_OF_RANGE",
                            f"{path}.ratio",
                            f"ratio ({ratio}) must be in [0, 1].",
                        ))
                elif den is None or den < 1:
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
            if item.get("evidence_span_ids"):
                issues.append(_warn(
                    "NON_EVALUABLE_HAS_EVIDENCE",
                    f"{path}.evidence_span_ids",
                    f"{status} item should have empty evidence_span_ids.",
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

    # evidence_span_ids must be non-empty and valid for micro_experiment.
    # Strengths and focus are now HighlightItems ({pattern_id, message} only).
    # Exception: conversational_balance is holistic — evidence_span_ids should be empty.
    for key, items in [("micro_experiment", micro_experiment)]:
        for i, item in enumerate(items):
            es_ids = item.get("evidence_span_ids", [])
            is_conv_balance = item.get("pattern_id") == "conversational_balance"
            if not es_ids and not is_conv_balance:
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
