from __future__ import annotations

from celery import Celery

from app.common.config import get_settings


settings = get_settings()

celery_app = Celery(
    "toolhub",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.task_worker"],
)
celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=False,
)

