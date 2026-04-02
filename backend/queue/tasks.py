"""
queue/tasks.py — Celery tasks that delegate to core workers.

Each task wraps exactly one worker function and handles:
- Error logging
- Airtable status updates on failure
- Celery retry on transient errors
"""
from __future__ import annotations

import logging
from typing import Optional

import anthropic
from celery import Task
from celery.exceptions import MaxRetriesExceededError
from requests.exceptions import HTTPError

from .celery_app import celery_app
from ..core.models import Gate1FailureError

logger = logging.getLogger(__name__)


def _is_retryable(exc: Exception) -> bool:
    """Return True only for transient errors worth retrying.

    Non-retryable cases (fail immediately):
    - Gate1 validation failures
    - 400 billing/credit errors
    - 401 authentication errors
    - 403 permission errors
    - Any other 4xx client error (except 429 rate limit)
    """
    if isinstance(exc, Gate1FailureError):
        return False
    if isinstance(exc, anthropic.RateLimitError):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return exc.status_code in {429, 500, 502, 503, 504, 529}
    if isinstance(exc, (anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return True
    # Airtable / requests HTTP errors: only retry on server errors and rate limits
    if isinstance(exc, HTTPError) and exc.response is not None:
        return exc.response.status_code in {429, 500, 502, 503, 504}
    # Unknown errors: retry to be safe
    return True


class BaseWorkerTask(Task):
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "Task %s[%s] failed: %s",
            self.name, task_id, exc, exc_info=einfo,
        )


@celery_app.task(
    name="backend.queue.tasks.process_single_meeting_task",
    bind=True,
    base=BaseWorkerTask,
    max_retries=0,
    default_retry_delay=15,
)
def enqueue_single_meeting(self, run_request_id: str) -> str:
    """
    Process a single_meeting analysis run.

    No Celery-level retries (max_retries=0). Transient errors are handled
    by the LLM client retry loop (LLM_RETRY_ATTEMPTS).

    Returns:
        Airtable run record ID.
    """
    from ..core.airtable_client import AirtableClient
    from ..core.workers import process_single_meeting_analysis

    try:
        run_id = process_single_meeting_analysis(run_request_id)
        return run_id
    except Exception as exc:
        logger.exception(
            "Single meeting analysis failed for run_request %s", run_request_id
        )
        try:
            AirtableClient().update_run_request_status(
                run_request_id, "error", error=str(exc)[:2000],
            )
        except Exception:
            pass
        raise


@celery_app.task(
    name="backend.queue.tasks.process_baseline_pack_task",
    bind=True,
    base=BaseWorkerTask,
    max_retries=0,
    default_retry_delay=30,
)
def enqueue_baseline_pack_build(self, baseline_pack_id: str) -> str:
    """
    Build a baseline pack.

    No Celery-level retries (max_retries=0). Transient errors are handled
    by the LLM client retry loop (LLM_RETRY_ATTEMPTS). Re-running the
    entire task is too expensive for baseline packs.

    Returns:
        Airtable run record ID for the baseline pack run.
    """
    from ..core.airtable_client import AirtableClient
    from ..core.workers import process_baseline_pack_build

    try:
        run_id = process_baseline_pack_build(baseline_pack_id)
        return run_id
    except Exception as exc:
        logger.exception(
            "Baseline pack build failed for pack %s", baseline_pack_id
        )
        try:
            AirtableClient().update_baseline_pack(baseline_pack_id, {"Status": "error"})
        except Exception:
            pass
        raise


@celery_app.task(
    name="backend.queue.tasks.process_next_experiment_suggestion_task",
    bind=True,
    base=BaseWorkerTask,
    max_retries=2,
    default_retry_delay=10,
    queue="single_meeting",
)
def enqueue_next_experiment_suggestion(self, user_record_id: str, just_parked_experiment_id: Optional[str] = None) -> Optional[str]:
    """
    Generate and propose next micro-experiments for a user after they
    complete or park their current experiment.

    Args:
        user_record_id: The user to generate experiments for.
        just_parked_experiment_id: If the trigger was a park action, the
            experiment that was just parked. Used to demote it from the
            top-pick slot in the options ranking.

    Returns:
        First Airtable experiment record ID, or None if skipped (e.g. user
        already has proposed experiments in the queue or is at the parked cap).
    """
    from ..core.workers import process_next_experiment_suggestion

    try:
        exp_record_id = process_next_experiment_suggestion(
            user_record_id,
            just_parked_experiment_id=just_parked_experiment_id,
        )
        return exp_record_id
    except Exception as exc:
        logger.exception(
            "Next experiment suggestion failed for user %s", user_record_id
        )

        if not _is_retryable(exc):
            logger.error(
                "Non-retryable error for experiment suggestion (user %s): %s",
                user_record_id, exc,
            )
            raise

        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise
