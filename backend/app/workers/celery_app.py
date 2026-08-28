import os
from celery import Celery
from app.core.config import settings

# Default to localhost for bare metal dev, docker-compose overrides this via env var
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "analyzer_tasks",
    broker=redis_url,
    backend=redis_url,
    include=["app.workers.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_concurrency=2, # Keep low for CPU-bound local testing
)
