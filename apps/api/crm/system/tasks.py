from celery import shared_task

from crm.system import services


@shared_task(name="system.record_heartbeat")
def record_heartbeat(component: str) -> None:
    services.record_heartbeat(component)
