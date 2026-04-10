"""Celery application configuration."""

from celery import Celery
from ...config import settings

# Create Celery app
celery_app = Celery(
    "olimpqr",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend or settings.celery_broker_url,
    include=[
        "olimpqr.infrastructure.tasks.ocr_tasks",
        "olimpqr.infrastructure.tasks.badge_tasks",
    ]
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max
    worker_prefetch_multiplier=1,
)
