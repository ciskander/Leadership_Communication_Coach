"""
queue/tasks.py — Celery tasks that delegate to core workers.

Each task wraps exactly one worker function and handles:
- Error logging
- Airtable status updates on failure
- Celery retry on transient errors
"""
from __future__ import annotations

import logging

from celery import Task
from celery.exceptions import MaxRetriesExceededError

from .celery_app import celery_app

logger = logging.getLogger(__name__)


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
    max_retries=3,
    default_retry_delay=15,
)
def enqueue_single_meeting(self, run_request_id: str) -> str:
    """
    Process a single_meeting analysis run.

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
        # Mark run_request as error in Airtable (best-effort)
        try:
            client = AirtableClient()
            client.update_run_request_status(
                run_request_id,
                "error",
                error=str(exc)[:2000],
            )
        except Exception:
            pass

        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise


@celery_app.task(
    name="backend.queue.tasks.process_baseline_pack_task",
    bind=True,
    base=BaseWorkerTask,
    max_retries=2,
    default_retry_delay=30,
)
def enqueue_baseline_pack_build(self, baseline_pack_id: str) -> str:
    """
    Build a baseline pack.

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
        # Mark baseline pack as error in Airtable (best-effort)
        try:
            client = AirtableClient()
            client.update_baseline_pack(baseline_pack_id, {"Status": "error"})
        except Exception:
            pass

        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            raise
