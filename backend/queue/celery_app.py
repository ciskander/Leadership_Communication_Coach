"""
queue/celery_app.py — Celery application configuration.
"""
from __future__ import annotations

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "leadership_coach",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,       # one task at a time per worker
    task_routes={
        "backend.queue.tasks.process_single_meeting_task": {"queue": "single_meeting"},
        "backend.queue.tasks.process_baseline_pack_task": {"queue": "baseline_pack"},
    },
    # Retry on transient failures
    task_max_retries=3,
    task_default_retry_delay=10,        # seconds
)
