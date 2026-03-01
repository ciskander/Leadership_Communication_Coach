"""
airtable_client.py — Typed Airtable CRUD with retry logic.

Uses pyairtable library. All field name constants are defined here.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from pyairtable import Api

from .config import (
    AIRTABLE_BASE_ID,
    AIRTABLE_TOKEN,
    AT_TABLE_BASELINE_PACK_ITEMS,
    AT_TABLE_BASELINE_PACKS,
    AT_TABLE_CONFIG,
    AT_TABLE_EXPERIMENT_EVENTS,
    AT_TABLE_EXPERIMENTS,
    AT_TABLE_RUN_REQUESTS,
    AT_TABLE_RUNS,
    AT_TABLE_TRANSCRIPTS,
    AT_TABLE_USERS,
    AT_TABLE_VALIDATION_ISSUES,
    RETRY_ATTEMPTS,
    RETRY_BASE_DELAY,
    RETRY_MAX_DELAY,
)
from .models import (
    BaselinePack,
    BaselinePackItem,
    Experiment,
    ExperimentEvent,
    Run,
    RunRequest,
    ValidationIssue as ValidationIssueModel,
)

logger = logging.getLogger(__name__)

# ── Field name constants ──────────────────────────────────────────────────────
# transcripts
F_TRANSCRIPT_ID = "Transcript ID"
F_TRANSCRIPT_TITLE = "Title"
F_TRANSCRIPT_ANALYSIS_TYPE = "Analysis Type"
F_TRANSCRIPT_MEETING_TYPE = "Meeting Type"
F_TRANSCRIPT_TARGET_ROLE = "Target Role"
F_TRANSCRIPT_MEETING_DATE = "Meeting Date"
F_TRANSCRIPT_RAW_TEXT = "Raw Transcript Text"
F_TRANSCRIPT_EXTRACTED = "Transcript (extracted)"
F_TRANSCRIPT_FILE = "Transcript File"

# run_requests
F_RR_REQUEST_ID = "Request ID"
F_RR_TRANSCRIPT = "Transcript"              # Link
F_RR_TARGET_SPEAKER_NAME = "Target Speaker Name"
F_RR_TARGET_SPEAKER_LABEL = "Target Speaker Label"
F_RR_TARGET_ROLE = "Target Role"
F_RR_ANALYSIS_TYPE = "Analysis Type"
F_RR_CONFIG = "Config"                       # Link
F_RR_STATUS = "Status"
F_RR_RUN = "Run"                             # Link
F_RR_BASELINE_PACK = "Baseline Pack"         # Link
F_RR_USER = "User"                           # Link
F_RR_ERROR = "Error"
F_RR_ACTIVE_EXPERIMENT = "Active Experiment" # Link
F_RR_EXP_ID_FROM_AE = "Experiment ID (from Active Experiment)"

# runs
F_RUN_RUN_ID = "Run ID"
F_RUN_TRANSCRIPT = "Transcript ID"           # Link
F_RUN_MODEL_NAME = "Model Name"
F_RUN_REQUEST_PAYLOAD = "Request Payload JSON"
F_RUN_RAW_OUTPUT = "Raw Model Output"
F_RUN_PARSED_JSON = "Parsed JSON"
F_RUN_PARSE_OK = "Parse OK"
F_RUN_SCHEMA_OK = "Schema OK"
F_RUN_BUSINESS_OK = "Business OK"
F_RUN_GATE1_PASS = "Gate1 Pass"
F_RUN_SCHEMA_VERSION_OUT = "Schema Version Out"
F_RUN_FOCUS_PATTERN = "Focus Pattern"
F_RUN_MICRO_EXP_PATTERN = "Micro-Experiment Pattern"
F_RUN_STRENGTHS_PATTERNS = "Strengths Patterns"
F_RUN_EVALUATED_COUNT = "Evaluated Patterns Count"
F_RUN_EVIDENCE_SPAN_COUNT = "Evidence Span Count"
F_RUN_CONFIG_USED = "Config Used"            # Link
F_RUN_BASELINE_PACK = "baseline_pack"        # Link
F_RUN_TARGET_SPEAKER_NAME = "Target Speaker Name"
F_RUN_TARGET_SPEAKER_LABEL = "Target Speaker Label"
F_RUN_TARGET_SPEAKER_ROLE = "Target Speaker Role"
F_RUN_ANALYSIS_TYPE = "Analysis Type"
F_RUN_ATTEMPT_MODEL = "Attempt (model)"
F_RUN_EXPERIMENT_STATUS_MODEL = "Experiment Status (model)"
F_RUN_EXPERIMENT_ID_OUT = "Experiment ID Out"
F_RUN_IDEMPOTENCY_KEY = "Idempotency Key"
F_RUN_COACHEE_ID = "Coachee ID"
F_RUN_RUN_REQUESTS = "run_requests"          # Link
F_RUN_EXPERIMENT_INSTANTIATED = "Experiment Instantiated?"
F_RUN_ATTEMPT_EVENT_CREATED = "Attempt Event Created?"

# validation_issues
F_VI_ISSUE_ID = "Issue ID"
F_VI_RUN = "Run ID"                          # Link
F_VI_SEVERITY = "Severity"
F_VI_ISSUE_CODE = "Issue Code"
F_VI_PATH = "Path"
F_VI_MESSAGE = "Message"

# baseline_packs
F_BP_PACK_ID = "Baseline Pack ID"
F_BP_CLIENT_NAME = "Client / Leader Name"
F_BP_TARGET_ROLE = "Target Role"
F_BP_STATUS = "Status"
F_BP_SPEAKER_LABEL = "Speaker Label"
F_BP_ACTIVE_EXPERIMENT = "Active Experiment"  # Link
F_BP_LAST_RUN = "Last Run"                    # Link
F_BP_ROLE_CONSISTENCY = "Role Consistency"
F_BP_MEETING_TYPE_CONSISTENCY = "Meeting Type Consistency"

# baseline_pack_items
F_BPI_ITEM_ID = "Baseline Pack Item ID"
F_BPI_BASELINE_PACK = "Baseline Pack"        # Link
F_BPI_TRANSCRIPT = "Transcript"              # Link
F_BPI_RUN = "Run"                            # Link
F_BPI_MEETING_SUMMARY = "Meeting Summary JSON"
F_BPI_STATUS = "Status"

# experiments
F_EXP_EXPERIMENT_ID = "Experiment ID"
F_EXP_TITLE = "Title"
F_EXP_INSTRUCTIONS = "Instructions"
F_EXP_SUCCESS_CRITERIA = "Success Criteria"
F_EXP_PATTERN_ID = "Pattern ID"
F_EXP_STATUS = "Status"
F_EXP_BASELINE_PACK = "Baseline Pack"        # Link
F_EXP_PROPOSED_BY_RUN = "Proposed By Run"    # Link
F_EXP_CREATED_FROM_RUN_ID = "Created From Run ID"
F_EXP_USER = "User"                          # Link
F_EXP_INSTRUCTION = "Instruction"
F_EXP_SUCCESS_MARKER = "Success Marker"

# experiment_events
F_EE_EVENT_ID = "Event ID"
F_EE_EXPERIMENT = "Experiment"               # Link
F_EE_USER = "User"                           # Link
F_EE_TRANSCRIPT = "Transcript"              # Link
F_EE_RUN = "Run"                             # Link
F_EE_MEETING_DATE = "Meeting Date"
F_EE_DETECTION_MODEL = "Detection (Model)"
F_EE_EVIDENCE_SPAN_IDS = "Evidence Span IDs (Model)"
F_EE_IDEMPOTENCY_KEY = "Idempotency Key"
F_EE_ATTEMPT_ENUM = "Attempt Enum"
F_EE_ATTEMPT_COUNT = "Attempt Count"

# users
F_USER_USER_ID = "User ID"
F_USER_DISPLAY_NAME = "Display Name"
F_USER_EMAIL = "Email"
F_USER_STATUS = "Status"
F_USER_TARGET_SPEAKER_NAME = "Target Speaker Name"
F_USER_TARGET_SPEAKER_LABEL = "Target Speaker Label"
F_USER_ACTIVE_BASELINE_PACK = "Active Baseline Pack"  # Link
F_USER_ACTIVE_EXPERIMENT = "Active Experiment"         # Link

# config
F_CFG_CONFIG_NAME = "Config Name"
F_CFG_ACTIVE = "Active"
F_CFG_MODEL_NAME = "Model Name"
F_CFG_SYSTEM_PROMPT = "System Prompt"
F_CFG_TAXONOMY_COMPACT = "Taxonomy Compact Block"
F_CFG_SCHEMA_VERSION = "Schema Version"
F_CFG_MAX_OUTPUT_TOKENS = "Max Output Tokens"


# ── Retry decorator ───────────────────────────────────────────────────────────

import functools
import requests


def _retryable(func):
    """Retry on 429 / 5xx responses with exponential backoff + jitter."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import random
        last_exc = None
        for attempt in range(RETRY_ATTEMPTS):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                # pyairtable raises HTTPError for 4xx/5xx
                status = None
                if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
                    status = exc.response.status_code
                if status in (429, 500, 502, 503, 504) or isinstance(
                    exc, (ConnectionError, TimeoutError)
                ):
                    last_exc = exc
                    delay = min(RETRY_BASE_DELAY * (2 ** attempt), RETRY_MAX_DELAY)
                    jitter = delay * 0.25 * (2 * random.random() - 1)
                    wait = delay + jitter
                    logger.warning(
                        "Airtable error (status=%s) attempt %d/%d; sleeping %.1fs: %s",
                        status, attempt + 1, RETRY_ATTEMPTS, wait, exc,
                    )
                    time.sleep(wait)
                else:
                    raise
        raise last_exc or RuntimeError("Airtable call failed after all retries.")
    return wrapper


# ── Client wrapper ────────────────────────────────────────────────────────────

class AirtableClient:
    """
    Typed Airtable client wrapping pyairtable.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        base_id: Optional[str] = None,
    ):
        self._api = Api(token or AIRTABLE_TOKEN)
        self._base_id = base_id or AIRTABLE_BASE_ID

    def _table(self, table_name: str):
        return self._api.table(self._base_id, table_name)

    # ── Generic helpers ───────────────────────────────────────────────────────

    @_retryable
    def get_record(self, table_name: str, record_id: str) -> dict:
        return self._table(table_name).get(record_id)

    @_retryable
    def create_record(self, table_name: str, fields: dict) -> dict:
        return self._table(table_name).create(fields)

    @_retryable
    def update_record(self, table_name: str, record_id: str, fields: dict) -> dict:
        return self._table(table_name).update(record_id, fields)

    @_retryable
    def search_records(
        self,
        table_name: str,
        formula: str,
        fields: Optional[list[str]] = None,
        max_records: int = 10,
    ) -> list[dict]:
        kwargs: dict = {"formula": formula, "max_records": max_records}
        if fields:
            kwargs["fields"] = fields
        return list(self._table(table_name).all(**kwargs))

    # ── Transcripts ───────────────────────────────────────────────────────────

    def get_transcript(self, record_id: str) -> dict:
        return self.get_record(AT_TABLE_TRANSCRIPTS, record_id)

    # ── Run Requests ──────────────────────────────────────────────────────────

    def get_run_request(self, record_id: str) -> dict:
        return self.get_record(AT_TABLE_RUN_REQUESTS, record_id)

    def update_run_request_status(self, record_id: str, status: str, error: Optional[str] = None, run_record_id: Optional[str] = None) -> dict:
        fields: dict = {F_RR_STATUS: status}
        if error:
            fields[F_RR_ERROR] = error
        if run_record_id:
            fields[F_RR_RUN] = [run_record_id]
        return self.update_record(AT_TABLE_RUN_REQUESTS, record_id, fields)

    # ── Runs ──────────────────────────────────────────────────────────────────

    def create_run(self, fields: dict) -> dict:
        return self.create_record(AT_TABLE_RUNS, fields)

    def update_run(self, record_id: str, fields: dict) -> dict:
        return self.update_record(AT_TABLE_RUNS, record_id, fields)

    def get_run(self, record_id: str) -> dict:
        return self.get_record(AT_TABLE_RUNS, record_id)

    def find_run_by_idempotency_key(self, key: str) -> Optional[dict]:
        formula = f"{{Idempotency Key}} = '{key}'"
        records = self.search_records(AT_TABLE_RUNS, formula, max_records=1)
        return records[0] if records else None

    def find_runs_for_baseline_pack(self, baseline_pack_record_id: str) -> list[dict]:
        formula = f"FIND('{baseline_pack_record_id}', ARRAYJOIN({{baseline_pack}}))"
        return self.search_records(AT_TABLE_RUNS, formula, max_records=5)

    # ── Validation Issues ─────────────────────────────────────────────────────

    def create_validation_issue(self, run_record_id: str, issue: ValidationIssueModel) -> dict:
        return self.create_record(AT_TABLE_VALIDATION_ISSUES, {
            F_VI_RUN: [run_record_id],
            F_VI_SEVERITY: issue.severity,
            F_VI_ISSUE_CODE: issue.issue_code,
            F_VI_PATH: issue.path,
            F_VI_MESSAGE: issue.message,
        })

    def bulk_create_validation_issues(self, run_record_id: str, issues: list[ValidationIssueModel]) -> None:
        for issue in issues:
            self.create_validation_issue(run_record_id, issue)

    # ── Baseline Packs ────────────────────────────────────────────────────────

    def get_baseline_pack(self, record_id: str) -> dict:
        return self.get_record(AT_TABLE_BASELINE_PACKS, record_id)

    def get_baseline_pack_by_pack_id(self, pack_id: str) -> Optional[dict]:
        formula = f"{{{F_BP_PACK_ID}}} = '{pack_id}'"
        records = self.search_records(AT_TABLE_BASELINE_PACKS, formula, max_records=1)
        return records[0] if records else None

    def update_baseline_pack(self, record_id: str, fields: dict) -> dict:
        return self.update_record(AT_TABLE_BASELINE_PACKS, record_id, fields)

    def get_baseline_pack_items(self, baseline_pack_record_id: str) -> list[dict]:
        formula = f"FIND('{baseline_pack_record_id}', ARRAYJOIN({{BP Record ID}}))"
        return self.search_records(AT_TABLE_BASELINE_PACK_ITEMS, formula, max_records=10)

    def get_baseline_pack_item(self, record_id: str) -> dict:
        return self.get_record(AT_TABLE_BASELINE_PACK_ITEMS, record_id)

    def update_baseline_pack_item(self, record_id: str, fields: dict) -> dict:
        return self.update_record(AT_TABLE_BASELINE_PACK_ITEMS, record_id, fields)

    # ── Experiments ───────────────────────────────────────────────────────────

    def create_experiment(self, fields: dict) -> dict:
        return self.create_record(AT_TABLE_EXPERIMENTS, fields)

    def get_experiment(self, record_id: str) -> dict:
        return self.get_record(AT_TABLE_EXPERIMENTS, record_id)

    def update_experiment(self, record_id: str, fields: dict) -> dict:
        return self.update_record(AT_TABLE_EXPERIMENTS, record_id, fields)

    def find_experiment_by_run_id(self, run_id: str) -> Optional[dict]:
        formula = f"{{{F_EXP_CREATED_FROM_RUN_ID}}} = '{run_id}'"
        records = self.search_records(AT_TABLE_EXPERIMENTS, formula, max_records=1)
        return records[0] if records else None

    def get_active_experiment_for_user(self, user_record_id: str) -> Optional[dict]:
        user = self.get_record(AT_TABLE_USERS, user_record_id)
        exp_links = user.get("fields", {}).get(F_USER_ACTIVE_EXPERIMENT, [])
        if not exp_links:
            return None
        return self.get_experiment(exp_links[0])

    # ── Experiment Events ─────────────────────────────────────────────────────

    def create_experiment_event(self, fields: dict) -> dict:
        return self.create_record(AT_TABLE_EXPERIMENT_EVENTS, fields)

    def find_experiment_event_by_idempotency_key(self, key: str) -> Optional[dict]:
        formula = f"{{{F_EE_IDEMPOTENCY_KEY}}} = '{key}'"
        records = self.search_records(AT_TABLE_EXPERIMENT_EVENTS, formula, max_records=1)
        return records[0] if records else None

    # ── Users ─────────────────────────────────────────────────────────────────

    def get_user(self, record_id: str) -> dict:
        return self.get_record(AT_TABLE_USERS, record_id)

    def update_user(self, record_id: str, fields: dict) -> dict:
        return self.update_record(AT_TABLE_USERS, record_id, fields)

    def set_active_experiment_for_user(self, user_record_id: str, experiment_record_id: str) -> dict:
        return self.update_user(user_record_id, {F_USER_ACTIVE_EXPERIMENT: [experiment_record_id]})

    # ── Config ────────────────────────────────────────────────────────────────

    def get_active_config(self, config_name: Optional[str] = None) -> Optional[dict]:
        if config_name:
            formula = f"AND({{{F_CFG_CONFIG_NAME}}} = '{config_name}', {{{F_CFG_ACTIVE}}})"
        else:
            formula = f"{{{F_CFG_ACTIVE}}}"
        records = self.search_records(AT_TABLE_CONFIG, formula, max_records=1)
        return records[0] if records else None
