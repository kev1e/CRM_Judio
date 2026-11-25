from uuid import UUID

from celery import Task, shared_task

from crm.identity import auth
from crm.telegram.gateway import TelegramUnavailableError

# The prompt is useful only for 3 minutes: a few quick retries, then give up.
_RETRY_DELAY_SECONDS = 5
_MAX_RETRIES = 3


@shared_task(name="identity.deliver_login_challenge", bind=True, max_retries=_MAX_RETRIES)
def deliver_login_challenge(self: Task[[str], None], challenge_id: str) -> None:
    """Send the Telegram approval prompt for a login attempt.

    The payload is only an ID; everything else is re-read and re-checked here.
    """
    challenge_pk = UUID(challenge_id)
    try:
        auth.deliver_challenge(challenge_pk)
    except TelegramUnavailableError:
        if self.request.retries >= _MAX_RETRIES:
            # Fail closed: without the prompt nobody can approve this login.
            auth.mark_delivery_failed(challenge_pk, reason="telegram_unavailable")
            return
        raise self.retry(countdown=_RETRY_DELAY_SECONDS) from None
