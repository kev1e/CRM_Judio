from celery import shared_task

from crm.tasks import services


@shared_task(name="tasks.archive_completed")
def archive_completed() -> int:
    """D041: archive tasks completed long enough ago. Idempotent; scheduled hourly."""
    return services.archive_completed()
