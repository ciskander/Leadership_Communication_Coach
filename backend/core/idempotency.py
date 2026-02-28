"""
idempotency.py — Idempotency key generation and check helpers.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional

from .airtable_client import (
    AirtableClient,
    F_EE_IDEMPOTENCY_KEY,
    F_EXP_CREATED_FROM_RUN_ID,
    F_RUN_IDEMPOTENCY_KEY,
)

logger = logging.getLogger(__name__)


def make_run_idempotency_key(
    transcript_id: str,
    analysis_type: str,
    coachee_id: str,
    target_speaker_label: str,
    target_role: str,
    config_version: str,
) -> str:
    """
    Composite SHA-256 key for a run record.
    Changing any component produces a different key, so a re-run with new params
    will create a new record.
    """
    raw = "|".join([
        transcript_id,
        analysis_type,
        coachee_id,
        target_speaker_label.lower().strip(),
        target_role,
        config_version,
    ])
    return hashlib.sha256(raw.encode()).hexdigest()


def make_experiment_event_key(run_id: str, experiment_id: str) -> str:
    raw = f"{run_id}|{experiment_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


def make_baseline_pack_run_key(baseline_pack_id: str) -> str:
    """One build run per baseline_pack_id."""
    return hashlib.sha256(baseline_pack_id.encode()).hexdigest()


# ── Check helpers ─────────────────────────────────────────────────────────────

def check_run_exists(
    client: AirtableClient,
    transcript_id: str,
    analysis_type: str,
    coachee_id: str,
    target_speaker_label: str,
    target_role: str,
    config_version: str,
) -> Optional[dict]:
    """
    Return the existing run record if one matches the idempotency key, else None.
    """
    key = make_run_idempotency_key(
        transcript_id, analysis_type, coachee_id,
        target_speaker_label, target_role, config_version,
    )
    existing = client.find_run_by_idempotency_key(key)
    if existing:
        logger.info("Idempotency hit for run key=%s record=%s", key[:16], existing["id"])
    return existing


def check_experiment_exists(client: AirtableClient, run_id: str) -> Optional[dict]:
    """Return experiment record if already instantiated for this run_id."""
    existing = client.find_experiment_by_run_id(run_id)
    if existing:
        logger.info("Idempotency hit: experiment already exists for run_id=%s", run_id)
    return existing


def check_experiment_event_exists(
    client: AirtableClient,
    run_id: str,
    experiment_id: str,
) -> Optional[dict]:
    """Return experiment_event if already created for (run_id, experiment_id)."""
    key = make_experiment_event_key(run_id, experiment_id)
    existing = client.find_experiment_event_by_idempotency_key(key)
    if existing:
        logger.info("Idempotency hit: experiment_event exists for run_id=%s exp_id=%s", run_id, experiment_id)
    return existing
