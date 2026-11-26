from uuid import UUID

from celery import Task, shared_task

from crm.notifications import services
from crm.telegram.gateway import TelegramUnavailableError

# PROVISIONAL (Q23 leaves the numbers open): 5 retries, 30 s doubling up to 8 min.
MAX_RETRIES = 5
FIRST_DELAY_SECONDS = 30


@shared_task(name="notifications.deliver", bind=True, max_retries=MAX_RETRIES)
def deliver_notification(self: Task[[str], None], notification_id: str) -> None:
    """Send one notification. The payload is only an ID; the recipient's rights
    and the text are read at this moment."""
    pk = UUID(notification_id)
    try:
        services.deliver(pk)
    except TelegramUnavailableError:
        if self.request.retries >= MAX_RETRIES:
            services.give_up(pk)
            return
        raise self.retry(countdown=FIRST_DELAY_SECONDS * 2**self.request.retries) from None
