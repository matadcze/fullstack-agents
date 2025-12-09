from celery import Celery

from src.core.config import settings

celery_app = Celery(
    "{{PROJECT_NAME_SLUG}}",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["src.worker.tasks"],
)

# JSON serialization for safety
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
