"""
queue/worker.py — Worker process entry point.

Run with:
  celery -A backend.queue.worker worker --loglevel=info -Q single_meeting,baseline_pack

Or for a simple single-queue worker:
  celery -A backend.queue.worker worker --loglevel=info
"""
from __future__ import annotations

import logging

# Import tasks so Celery discovers them
from .tasks import enqueue_single_meeting, enqueue_baseline_pack_build  # noqa: F401
from .celery_app import celery_app  # noqa: F401

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
