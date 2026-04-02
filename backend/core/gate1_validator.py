"""
gate1_validator.py — Strict JSON schema + business rule validation for LLM output (v0.4.0).

Includes a lightweight sanitisation pass that corrects known LLM enum
confusions *before* schema validation so that minor hallucinated enum values
do not cause otherwise-valid output to fail Gate1.

v0.4.0 changes from v0.3.0:
- OEs are top-level (not nested in pattern_snapshot)
- pattern_snapshot is scoring only (no coaching fields)
- coaching_output → coaching (unified coaching section)
- Evidence span IDs are turn-anchored: ^ES-T[0-9]+(-[0-9]+)?$
- Three-way consistency graph: span→OE, OE→pattern, success classification
"""
from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
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

# Scoring-only validator: schema with coaching and experiment_tracking not required
def _build_scoring_only_schema() -> dict:
    """Create a variant of the main schema that does not require coaching or experiment_tracking.

    Used for Gate 1 validation of Stage 1 (scoring-only) output.
    """
    import copy
    schema = copy.deepcopy(_SCHEMA)
    # Remove coaching and experiment_tracking from required top-level keys
    if "required" in schema:
        schema["required"] = [
            k for k in schema["required"]
            if k not in ("coaching", "experiment_tracking")
        ]
    # Remove coaching and experiment_tracking from properties if they have
    # sub-schema validation that would fail on missing data
    # (keeping them in properties is fine — they just won't be required)
    return schema


_SCORING_SCHEMA: dict = _build_scoring_only_schema()
_SCORING_VALIDATOR = Draft202012Validator(_SCORING_SCHEMA)

# ── ID format regexes ─────────────────────────────────────────────────────────
_ID_PATTERNS = {
    "analysis_id": re.compile(r"^A-\d{6}$"),
    "meeting_id": re.compile(r"^M-\d{6}$"),
    "baseline_pack_id": re.compile(r"^BP-\d{6}$"),
    "experiment_id": re.compile(r"^EXP-\d{6}$"),
    "evidence_span_id": re.compile(r"^E(S|XD)-T[0-9]+(-[0-9]+)?$"),
}

_PATTERN_ID_ENUM = set(PATTERN_ORDER)

_SCORED_PATTERNS = set(PATTERN_ORDER)


def _issue(severity: str, code: str, path: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity=severity, issue_code=code, path=path, message=message)


def _err(code: str, path: str, message: str) -> ValidationIssue:
    return _issue("error", code, path, message)


def _warn(code: str, path: str, message: str) -> ValidationIssue:
    return _issue("warning", code, path, message)


# ── Helpers for span/rewrite consistency checks ─────────────────────────────

_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "that", "this", "these",
    "those", "it", "its", "they", "them", "their", "we", "our", "you",
    "your", "just", "also", "very", "really", "then", "than", "so", "if",
    "when", "what", "which", "who", "how", "about", "into", "over",
    "after", "before", "between", "through", "during", "think", "want",
    "going", "know", "like", "need", "make", "said", "says", "say",
    "here", "there", "some", "more", "still", "every", "each", "both",
    "does", "done", "being", "much", "well", "back", "even", "only",
})


def _extract_content_words(text: str) -> set[str]:
    """Extract meaningful content words (4+ chars, not stop words) from text."""
    words = set(re.findall(r"[a-zA-Z]{4,}", text.lower()))
    return words - _STOP_WORDS


# ── Pre-validation sanitiser ─────────────────────────────────────────────────

_VALID_TARGET_CONTROL = {"yes", "no", "unclear"}
_VALID_COUNT_DECISION = {"counted", "excluded"}
_VALID_SUCCESS_VALUES = {0, 0.0, 0.2, 0.25, 0.4, 0.5, 0.6, 0.75, 0.8, 1, 1.0}


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

    Uses SequenceMatcher similarity. Returns the closest allowed key if the
    similarity is >= 60%, otherwise None.
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

    # ── coaching section (v0.4.0: replaces coaching_output) ──────────────
    if "coaching" in data and isinstance(data["coaching"], dict):
        co = data["coaching"]
        fixes += _fix_extra_keys(co, _ALLOWED_KEYS.get("Coaching", set()), "$.coaching")
        # Coerce executive_summary from array to string (common LLM quirk)
        es = co.get("executive_summary")
        if isinstance(es, list):
            co["executive_summary"] = " ".join(str(item) for item in es if item)
            fixes += 1
        ci_keys = _ALLOWED_KEYS.get("HighlightItem", set())
        for i, s in enumerate(co.get("strengths", [])):
            if isinstance(s, dict):
                fixes += _fix_extra_keys(s, ci_keys, f"$.coaching.strengths[{i}]")
        # focus sanitisation removed in P2.4 — focus no longer in schema
        me_keys = _ALLOWED_KEYS.get("MicroExperiment", set())
        for i, m in enumerate(co.get("micro_experiment", [])):
            if isinstance(m, dict):
                fixes += _fix_extra_keys(m, me_keys, f"$.coaching.micro_experiment[{i}]")
        pc_keys = _ALLOWED_KEYS.get("PatternCoachingItem", set())
        for i, pc in enumerate(co.get("pattern_coaching", [])):
            if isinstance(pc, dict):
                fixes += _fix_extra_keys(pc, pc_keys, f"$.coaching.pattern_coaching[{i}]")
        ec = co.get("experiment_coaching")
        if isinstance(ec, dict):
            ec_keys = _ALLOWED_KEYS.get("ExperimentCoaching", set())
            fixes += _fix_extra_keys(ec, ec_keys, "$.coaching.experiment_coaching")

    # ── pattern_snapshot (scoring only in v0.4.0) ────────────────────────
    ps_keys = _ALLOWED_KEYS.get("PatternMeasurementBase", set())
    for i, item in enumerate(data.get("pattern_snapshot", [])):
        if isinstance(item, dict):
            fixes += _fix_extra_keys(item, ps_keys, f"$.pattern_snapshot[{i}]")

    # ── evidence_spans ───────────────────────────────────────────────────
    es_keys = _ALLOWED_KEYS.get("EvidenceSpan", set())
    for i, span in enumerate(data.get("evidence_spans", [])):
        if isinstance(span, dict):
            fixes += _fix_extra_keys(span, es_keys, f"$.evidence_spans[{i}]")

    # ── top-level opportunity_events (v0.4.0) ────────────────────────────
    oe_keys = _ALLOWED_KEYS.get("OpportunityEvent", set())
    for i, event in enumerate(data.get("opportunity_events", [])):
        if isinstance(event, dict):
            fixes += _fix_extra_keys(event, oe_keys, f"$.opportunity_events[{i}]")

    # ── experiment_tracking ──────────────────────────────────────────────
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

    # micro_experiment items (now under coaching, not coaching_output)
    for i, m in enumerate((data.get("coaching") or {}).get("micro_experiment", [])):
        if isinstance(m, dict):
            fixes += _fix_exp_id(m, "experiment_id", f"$.coaching.micro_experiment[{i}].experiment_id")

    # experiment_tracking.active_experiment
    ae = (data.get("experiment_tracking") or {}).get("active_experiment")
    if isinstance(ae, dict):
        fixes += _fix_exp_id(ae, "experiment_id", "$.experiment_tracking.active_experiment.experiment_id")

    # experiment_tracking.detection_in_this_meeting
    det = (data.get("experiment_tracking") or {}).get("detection_in_this_meeting")
    if isinstance(det, dict):
        fixes += _fix_exp_id(det, "experiment_id", "$.experiment_tracking.detection_in_this_meeting.experiment_id")

    # ── Coerce evaluable patterns missing score/opp_count to insufficient_signal ──
    ps_list = data.get("pattern_snapshot", [])
    eval_summary = data.get("evaluation_summary", {})
    evaluated_list = eval_summary.get("patterns_evaluated", [])
    insuff_list = eval_summary.get("patterns_insufficient_signal", [])
    for snap in ps_list:
        if (
            snap.get("evaluable_status") == "evaluable"
            and ("score" not in snap or "opportunity_count" not in snap)
        ):
            pid = snap.get("pattern_id", "?")
            logger.warning(
                "Sanitiser: coercing %s from evaluable to insufficient_signal "
                "(missing score or opportunity_count)",
                pid,
            )
            snap["evaluable_status"] = "insufficient_signal"
            snap.pop("score", None)
            snap.pop("opportunity_count", None)
            snap.pop("success_evidence_span_ids", None)
            snap.pop("simple_count", None)
            snap.pop("complex_count", None)
            snap["evidence_span_ids"] = []
            # Sync evaluation_summary arrays
            if pid in evaluated_list:
                evaluated_list.remove(pid)
                if pid not in insuff_list:
                    insuff_list.append(pid)
            fixes += 1

    # ── Strip OEs for non-evaluable patterns ────────────────────────────
    non_evaluable_pids = {
        p.get("pattern_id") for p in ps_list
        if p.get("evaluable_status") in ("insufficient_signal", "not_evaluable")
    }
    if non_evaluable_pids:
        original_oes = data.get("opportunity_events", [])
        stripped = [oe for oe in original_oes if oe.get("pattern_id") in non_evaluable_pids]
        if stripped:
            data["opportunity_events"] = [oe for oe in original_oes if oe.get("pattern_id") not in non_evaluable_pids]
            for oe in stripped:
                logger.warning(
                    "Sanitiser: stripping OE %s for non-evaluable pattern %s",
                    oe.get("event_id"), oe.get("pattern_id"),
                )
            fixes += len(stripped)

    # ── Fix known LLM enum confusions in top-level opportunity_events ────
    for event in data.get("opportunity_events", []):
        if not isinstance(event, dict):
            continue
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
        if cd is None:
            event["count_decision"] = "counted"
            logger.warning(
                "Sanitiser: missing count_decision → 'counted' (event %s)",
                event.get("event_id"),
            )
            fixes += 1
        elif cd not in _VALID_COUNT_DECISION:
            inferred = "counted" if cd in ("yes",) else "excluded"
            logger.warning(
                "Sanitiser: count_decision %r → %r (event %s)",
                cd, inferred, event.get("event_id"),
            )
            event["count_decision"] = inferred
            fixes += 1

        su = event.get("success")
        if su is not None and isinstance(su, str):
            # Convert legacy string values to numeric
            str_to_num = {"yes": 1.0, "no": 0.0, "na": 0.0}
            inferred = str_to_num.get(su, 0.0)
            logger.warning(
                "Sanitiser: success %r → %r (event %s)",
                su, inferred, event.get("event_id"),
            )
            event["success"] = inferred
            fixes += 1

    # ── Null out detection_in_this_meeting when no active experiment ─────
    et = data.get("experiment_tracking")
    if isinstance(et, dict):
        ae = et.get("active_experiment")
        if isinstance(ae, dict) and ae.get("status") == "none":
            det = et.get("detection_in_this_meeting")
            if det is not None:
                logger.warning(
                    "Sanitiser: detection_in_this_meeting set to null "
                    "(active_experiment.status=none)",
                )
                et["detection_in_this_meeting"] = None
                fixes += 1

    # ── experiment_coaching: [] → null ────────────────────────────────────
    co = data.get("coaching")
    if isinstance(co, dict):
        ec = co.get("experiment_coaching")
        if isinstance(ec, list) and len(ec) == 0:
            logger.warning("Sanitiser: experiment_coaching [] → null")
            co["experiment_coaching"] = None
            fixes += 1

    # ── reason_code: replace spaces with underscores ─────────────────────
    for event in data.get("opportunity_events", []):
        if not isinstance(event, dict):
            continue
        rc = event.get("reason_code")
        if isinstance(rc, str) and " " in rc:
            fixed_rc = re.sub(r"\s+", "_", rc.strip()).lower()
            logger.warning(
                "Sanitiser: reason_code %r → %r (event %s)",
                rc, fixed_rc, event.get("event_id"),
            )
            event["reason_code"] = fixed_rc
            fixes += 1

    if fixes:
        logger.info("Sanitiser applied %d fix(es) total.", fixes)
    return fixes


# ── Public entry point ────────────────────────────────────────────────────────

def validate(raw_text: str, *, mode: str = "full") -> Gate1Result:
    """
    Run the Gate1 validation pipeline.

    Args:
        raw_text: JSON string to validate.
        mode: Validation mode.
            - ``"full"``: Validate the complete output (scoring + coaching + experiment_tracking).
              This is the default and matches the existing behaviour.
            - ``"scoring_only"``: Validate scoring-only output from Stage 1.
              coaching and experiment_tracking are not required and coaching-related
              business rules are skipped.

    Steps:
        1. JSON parse
        1b. Sanitise known LLM enum confusions
        2. JSON Schema validation
        3. Business rules

    Returns:
        Gate1Result with passed flag and list of issues.
    """
    if mode not in ("full", "scoring_only"):
        raise ValueError(f"Invalid validation mode: {mode!r}. Must be 'full' or 'scoring_only'.")

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
    validator = _SCORING_VALIDATOR if mode == "scoring_only" else _VALIDATOR
    schema_errors = list(validator.iter_errors(data))
    for error in schema_errors:
        path = ".".join(str(p) for p in error.absolute_path) or "$"
        issues.append(_err("SCHEMA_VIOLATION", path, error.message))

    if issues:
        # Schema errors are fatal; skip business rules for cleaner reporting
        return Gate1Result(passed=False, issues=issues)

    # ── Step 3: Business rules (may auto-correct data in-place) ────────────────
    issues.extend(_business_rules(data, scoring_only=(mode == "scoring_only")))

    has_corrections = any(i.issue_code == "SCORE_ARITHMETIC_AUTOCORRECTED" for i in issues)
    passed = all(i.severity != "error" for i in issues)
    return Gate1Result(
        passed=passed,
        issues=issues,
        corrected_data=data if has_corrections else None,
    )


# Keep backward-compatible alias
gate1_validate = validate


# ── Success classification thresholds ─────────────────────────────────────────

_SUCCESS_THRESHOLDS = {
    "binary": 1.0,
    "tiered_rubric": 0.75,
    "complexity_tiered": 0.75,
    "multi_element": 0.8,
}

# ── Allowed per-type success values ──────────────────────────────────────────

_ALLOWED_SUCCESS = {
    "tiered_rubric":      {0, 0.25, 0.5, 0.75, 1.0},
    "binary":             {0, 1.0},
    "complexity_tiered":  {0, 0.25, 0.5, 0.75, 1.0},
    "multi_element":      {0, 0.2, 0.4, 0.6, 0.8, 1.0},
}

# Pattern-specific overrides for allowed success values
_PATTERN_ALLOWED_SUCCESS: dict[str, set[float]] = {
    "focus_management": {0, 0.5, 1.0},
}


def _business_rules(data: dict, *, scoring_only: bool = False) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    analysis_type = data.get("meta", {}).get("analysis_type", "")
    pattern_snapshot = data.get("pattern_snapshot", [])
    evidence_spans = data.get("evidence_spans", [])
    opportunity_events = data.get("opportunity_events", [])
    coaching = data.get("coaching", {}) if not scoring_only else {}
    experiment_tracking = data.get("experiment_tracking", {}) if not scoring_only else {}

    # ── Build lookup structures ──────────────────────────────────────────────
    valid_es_ids = {span.get("evidence_span_id") for span in evidence_spans}
    span_by_id = {span.get("evidence_span_id"): span for span in evidence_spans}
    oe_by_id = {oe.get("event_id"): oe for oe in opportunity_events}

    # OEs grouped by pattern_id (counted only)
    counted_oes_by_pattern: dict[str, list[dict]] = defaultdict(list)
    for oe in opportunity_events:
        if oe.get("count_decision") == "counted":
            counted_oes_by_pattern[oe.get("pattern_id", "")].append(oe)

    # Pattern lookup by pattern_id
    pattern_by_id = {p.get("pattern_id"): p for p in pattern_snapshot}

    # ── 3a. pattern_snapshot must have exactly N items in required order ──────
    expected_count = len(PATTERN_ORDER)
    if len(pattern_snapshot) != expected_count:
        issues.append(_err(
            "PATTERN_SNAPSHOT_COUNT",
            "pattern_snapshot",
            f"Expected {expected_count} items, got {len(pattern_snapshot)}.",
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

    # ── 3b. evaluation_summary arrays partition all pattern_ids ─────────────
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

    # ── 3c. Pattern snapshot item validation (scoring only) ──────────────────
    for idx, item in enumerate(pattern_snapshot):
        pid = item.get("pattern_id", "")
        path = f"pattern_snapshot[{idx}]"
        status = item.get("evaluable_status")

        if status == "evaluable":
            score = item.get("score")
            if score is None:
                issues.append(_err(
                    "MISSING_SCORE",
                    f"{path}.score",
                    "Evaluable pattern must have a score value.",
                ))
            elif not (0 <= score <= 1):
                issues.append(_err(
                    "SCORE_OUT_OF_RANGE",
                    f"{path}.score",
                    f"score ({score}) must be in [0, 1].",
                ))

        elif status in ("insufficient_signal", "not_evaluable"):
            if item.get("score") is not None:
                issues.append(_err(
                    "NON_EVALUABLE_HAS_SCORE",
                    f"{path}.score",
                    f"{status} item must not have score.",
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

    # ── 3c2. Top-level OE validation ─────────────────────────────────────────
    for ei, event in enumerate(opportunity_events):
        epath = f"opportunity_events[{ei}]"
        scoring_type = None
        epid = event.get("pattern_id", "")

        # Validate pattern_id references an evaluable pattern
        pattern = pattern_by_id.get(epid)
        if pattern:
            scoring_type = pattern.get("scoring_type")
            if pattern.get("evaluable_status") != "evaluable":
                issues.append(_warn(
                    "OE_FOR_NON_EVALUABLE",
                    epath,
                    f"OE references pattern '{epid}' which is not evaluable.",
                ))

        # Per-type success value validation (pattern-specific override first)
        if event.get("count_decision") == "counted" and scoring_type:
            allowed = _PATTERN_ALLOWED_SUCCESS.get(epid) or _ALLOWED_SUCCESS.get(scoring_type)
            if allowed is not None:
                sv = event.get("success", 0)
                if sv not in allowed:
                    issues.append(_warn(
                        "SUCCESS_VALUE_INVALID_FOR_TYPE",
                        f"{epath}.success",
                        f"success={sv} not in allowed set {sorted(allowed)} "
                        f"for scoring_type={scoring_type} (pattern={epid}).",
                    ))

    # ── 3c3. OE→pattern reconciliation + score arithmetic ────────────────────
    for idx, item in enumerate(pattern_snapshot):
        pid = item.get("pattern_id", "")
        path = f"pattern_snapshot[{idx}]"
        status = item.get("evaluable_status")

        if status != "evaluable":
            continue

        counted_oes = counted_oes_by_pattern.get(pid, [])
        counted_actual = len(counted_oes)
        opp_count = item.get("opportunity_count")

        # (b) OE → pattern: opportunity_count must match counted OEs
        #     (skip for baseline_pack — aggregate counts don't map to individual OEs)
        if analysis_type != "baseline_pack" and opp_count is not None and opp_count != counted_actual:
            item["opportunity_count"] = counted_actual
            issues.append(_warn(
                "OPP_COUNT_COUNTED_MISMATCH",
                f"{path}.opportunity_count",
                f"opportunity_count corrected from {opp_count} to {counted_actual} "
                f"for pattern '{pid}'.",
            ))

        # Score arithmetic auto-correction
        if counted_actual > 0:
            success_sum = sum(
                oe.get("success", 0) for oe in counted_oes
            )
            expected_score = round(success_sum / counted_actual, 4)
            actual_score = item.get("score")
            if actual_score is not None and abs(actual_score - expected_score) > 0.0005:
                # Auto-correct: trust the opportunity_events arithmetic
                item["score"] = expected_score
                issues.append(_warn(
                    "SCORE_ARITHMETIC_AUTOCORRECTED",
                    f"{path}.score",
                    f"score corrected from {actual_score} to {expected_score} "
                    f"(sum(success)/counted = {success_sum}/{counted_actual}).",
                ))

    # ── 3c4. Three-way consistency: span→OE, success classification ──────────
    # (a) span → OE: every span's event_ids must reference valid OE event_ids
    for si, span in enumerate(evidence_spans):
        for event_id in span.get("event_ids", []):
            if event_id not in oe_by_id:
                issues.append(_warn(
                    "SPAN_DANGLING_EVENT_ID",
                    f"evidence_spans[{si}].event_ids",
                    f"event_id '{event_id}' not found in opportunity_events.",
                ))

    # (c) success classification: deterministic rebuild
    for idx, item in enumerate(pattern_snapshot):
        pid = item.get("pattern_id", "")
        path = f"pattern_snapshot[{idx}]"
        status = item.get("evaluable_status")
        scoring_type = item.get("scoring_type", "")

        if status != "evaluable":
            continue

        threshold = _SUCCESS_THRESHOLDS.get(scoring_type, 0.75)
        pattern_es_ids = item.get("evidence_span_ids") or []
        actual_success_ids = set(item.get("success_evidence_span_ids") or [])

        # Walk: pattern → evidence_span_ids → span.event_ids → OE.success
        for es_id in pattern_es_ids:
            span = span_by_id.get(es_id)
            if not span:
                continue

            # Find max success score among OEs linked to this span for THIS pattern
            max_success = None
            for event_id in span.get("event_ids", []):
                oe = oe_by_id.get(event_id)
                if oe and oe.get("pattern_id") == pid and oe.get("count_decision") == "counted":
                    s = oe.get("success", 0)
                    if max_success is None or s > max_success:
                        max_success = s

            if max_success is None:
                continue

            is_success = max_success >= threshold
            in_success_list = es_id in actual_success_ids

            if is_success and not in_success_list:
                issues.append(_warn(
                    "SUCCESS_SPAN_MISSING",
                    f"{path}.success_evidence_span_ids",
                    f"{es_id} has OE score {max_success} (>= {threshold} threshold "
                    f"for {scoring_type}) but is not in success_evidence_span_ids.",
                ))
            elif not is_success and in_success_list:
                issues.append(_warn(
                    "SUCCESS_SPAN_INCORRECT",
                    f"{path}.success_evidence_span_ids",
                    f"{es_id} has OE score {max_success} (< {threshold} threshold "
                    f"for {scoring_type}) but IS in success_evidence_span_ids.",
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

    # ── 3d2. Excerpt length check (warning only — long excerpts are allowed) ──
    _EXCERPT_WARN_LEN = 2500
    for idx, span in enumerate(evidence_spans):
        excerpt = span.get("excerpt", "")
        if len(excerpt) > _EXCERPT_WARN_LEN:
            issues.append(_warn(
                "EXCERPT_LENGTH",
                f"evidence_spans[{idx}].excerpt",
                f"Excerpt is {len(excerpt)} chars (warning threshold {_EXCERPT_WARN_LEN}). "
                f"Long excerpts are allowed but may display poorly in the UI.",
            ))

    # ── 3c5–3f: Coaching and experiment checks (skipped for scoring-only) ────
    if not scoring_only:

        # ── 3c5. Rewrite checks on coaching.pattern_coaching ─────────────────
        for pci, pc in enumerate(coaching.get("pattern_coaching", [])):
            pc_path = f"coaching.pattern_coaching[{pci}]"
            pc_pid = pc.get("pattern_id", "")
            rewrite_span = pc.get("rewrite_for_span_id")

            if not rewrite_span:
                continue

            pattern = pattern_by_id.get(pc_pid)
            scoring_type = pattern.get("scoring_type", "") if pattern else ""
            threshold = _SUCCESS_THRESHOLDS.get(scoring_type, 0.75)

            # V2: rewrite_for_span_id should target a low-scored span
            span = span_by_id.get(rewrite_span)
            if span:
                for event_id in span.get("event_ids", []):
                    oe = oe_by_id.get(event_id)
                    if oe and oe.get("pattern_id") == pc_pid and oe.get("count_decision") == "counted":
                        if oe.get("success", 0) >= threshold:
                            issues.append(_warn(
                                "REWRITE_TARGETS_SUCCESS",
                                f"{pc_path}.rewrite_for_span_id",
                                f"rewrite_for_span_id {rewrite_span} maps to OE with "
                                f"score {oe.get('success', 0)} (>= {threshold} threshold for "
                                f"{scoring_type}). Rewrite should target a missed "
                                f"opportunity.",
                            ))
                        break

            # V3: rewrite/span content plausibility — zero content-word overlap
            if pc.get("suggested_rewrite") and span and span.get("excerpt"):
                excerpt_words = _extract_content_words(span["excerpt"])
                rewrite_words = _extract_content_words(pc["suggested_rewrite"])
                if (excerpt_words and rewrite_words
                        and len(excerpt_words) >= 3
                        and len(rewrite_words) >= 3
                        and not excerpt_words & rewrite_words):
                    issues.append(_warn(
                        "REWRITE_CONTENT_MISMATCH",
                        f"{pc_path}.suggested_rewrite",
                        f"suggested_rewrite shares no content words with the "
                        f"excerpt of {rewrite_span}. The rewrite may address "
                        f"a different topic.",
                    ))

        # ── 3c6. best_success_span_id checks on coaching.pattern_coaching ────
        for pci, pc in enumerate(coaching.get("pattern_coaching", [])):
            pc_path = f"coaching.pattern_coaching[{pci}]"
            pc_pid = pc.get("pattern_id", "")
            best_span = pc.get("best_success_span_id")

            pattern = pattern_by_id.get(pc_pid)
            if not pattern:
                continue

            success_ids = set(pattern.get("success_evidence_span_ids") or [])

            if best_span and best_span not in success_ids:
                issues.append(_warn(
                    "BEST_SUCCESS_SPAN_NOT_IN_SUCCESS_LIST",
                    f"{pc_path}.best_success_span_id",
                    f"best_success_span_id {best_span} is not in "
                    f"success_evidence_span_ids for pattern {pc_pid}.",
                ))

            # Auto-repair: if missing but success spans exist, pick the first one
            if not best_span and success_ids:
                pc["best_success_span_id"] = sorted(success_ids)[0]
                issues.append(_warn(
                    "BEST_SUCCESS_SPAN_AUTO_FILLED",
                    f"{pc_path}.best_success_span_id",
                    f"best_success_span_id was null/missing but success spans "
                    f"exist. Auto-filled with {pc['best_success_span_id']}.",
                ))

        # ── 3e. coaching cardinality ─────────────────────────────────────────
        strengths = coaching.get("strengths", [])
        micro_experiment = coaching.get("micro_experiment", [])

        if not (0 <= len(strengths) <= 2):
            issues.append(_err(
                "COACHING_STRENGTHS_COUNT",
                "coaching.strengths",
                f"strengths must have 0-2 items, got {len(strengths)}.",
            ))
        for si, s_item in enumerate(strengths):
            s_pid = s_item.get("pattern_id", "")
            s_pattern = pattern_by_id.get(s_pid)
            if s_pattern:
                s_score = s_pattern.get("score", 0)
                if s_score is not None and s_score < 0.70:
                    issues.append(_warn(
                        "STRENGTH_LOW_SCORE",
                        f"coaching.strengths[{si}]",
                        f"Pattern '{s_pid}' listed as strength but scores {s_score} "
                        f"(threshold 0.70).",
                    ))
        # focus validation removed in P2.4 — focus is no longer produced by Stage 2
        if len(micro_experiment) != 1:
            issues.append(_err(
                "COACHING_MICRO_EXP_COUNT",
                "coaching.micro_experiment",
                f"micro_experiment must have exactly 1 item, got {len(micro_experiment)}.",
            ))

        # evidence_span_ids must be non-empty and valid for micro_experiment.
        for key, items in [("micro_experiment", micro_experiment)]:
            for i, item in enumerate(items):
                es_ids = item.get("evidence_span_ids", [])
                if not es_ids and analysis_type != "baseline_pack":
                    issues.append(_err(
                        "COACHING_EMPTY_ES_IDS",
                        f"coaching.{key}[{i}].evidence_span_ids",
                        "evidence_span_ids must be non-empty in coaching items.",
                    ))
                for es_id in es_ids:
                    if es_id not in valid_es_ids:
                        issues.append(_err(
                            "COACHING_DANGLING_ES",
                            f"coaching.{key}[{i}].evidence_span_ids",
                            f"evidence_span_id {es_id} not found in evidence_spans.",
                        ))

        # ── 3f. Experiment tracking conditional rules ─────────────────────────
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
            if status in ("assigned", "active", "proposed"):
                if detection is None:
                    issues.append(_err(
                        "SINGLE_MEETING_DETECTION_REQUIRED",
                        "experiment_tracking.detection_in_this_meeting",
                        "active/proposed experiment requires detection_in_this_meeting to be non-null.",
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

    if not scoring_only:
        micro_experiment = coaching.get("micro_experiment", [])
        if micro_experiment:
            exp_id = micro_experiment[0].get("experiment_id")
            _check_id_format(data, "coaching.micro_experiment[0].experiment_id", exp_id, "experiment_id", issues)

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
