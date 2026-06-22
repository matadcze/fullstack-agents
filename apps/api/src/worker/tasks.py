"""
Celery background tasks.

This module defines Celery tasks for background processing.
Add your custom background tasks here following the example pattern.
"""

from src.core.logging import configure_logging, log_json
from src.core.time import utc_now

from .celery_app import celery_app


@celery_app.task(name="example.hello_world")
def hello_world_task() -> str:
    """Example Celery task."""
    configure_logging()
    log_json(
        celery_app.log.get_default_logger(),
        "example.task_executed",
        task="hello_world",
        at=str(utc_now()),
    )
    return "Hello from Celery!"


# Beat schedule configuration (for periodic tasks)
# Example: Run hello_world_task every 10 minutes
# from celery.schedules import crontab
# celery_app.conf.beat_schedule = {
#     "example-hello-world": {
#         "task": "example.hello_world",
#         "schedule": crontab(minute="*/10"),
#     }
# }
