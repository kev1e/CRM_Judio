import pytest
from celery.exceptions import Retry

from crm.audit.models import AuditEvent
from crm.conftest import Employee
from crm.identity import auth, tasks
from crm.identity.models import LoginChallenge
from crm.telegram.fake import FakeGateway
from crm.telegram.gateway import TelegramUnavailableError

pytestmark = pytest.mark.django_db


def start(employee: Employee) -> auth.StartedLogin:
    return auth.start_login(
        crm_login=employee.user.crm_login,
        password=employee.password,
        ip_address="203.0.113.5",
        user_agent="tests",
    )


def test_task_delivers_the_prompt(employee: Employee, fake_telegram: type[FakeGateway]) -> None:
    started = start(employee)

    tasks.deliver_login_challenge.apply(args=(str(started.challenge_id),)).get()

    assert len(fake_telegram.sent) == 1
    assert LoginChallenge.objects.get().delivery == "sent"


def test_task_retries_while_telegram_is_unavailable(
    employee: Employee, fake_telegram: type[FakeGateway]
) -> None:
    fake_telegram.failure = TelegramUnavailableError("TelegramNetworkError")
    started = start(employee)

    with pytest.raises(Retry):
        tasks.deliver_login_challenge.apply(args=(str(started.challenge_id),), throw=True).get()

    # Still waiting: a retry may succeed within the 3 minutes.
    assert LoginChallenge.objects.get().delivery == "pending"


def test_task_gives_up_after_the_last_retry_and_fails_closed(
    employee: Employee, fake_telegram: type[FakeGateway]
) -> None:
    fake_telegram.failure = TelegramUnavailableError("TelegramNetworkError")
    started = start(employee)

    tasks.deliver_login_challenge.apply(args=(str(started.challenge_id),), retries=3).get()

    assert LoginChallenge.objects.get().delivery == "failed"
    event = AuditEvent.objects.get(action="auth.challenge_delivery_failed")
    assert event.metadata["reason"] == "telegram_unavailable"
