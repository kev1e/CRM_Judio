import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from crm.access import services
from crm.access.models import UserRole
from crm.access.permissions import ADMINISTRATOR_GRANTS
from crm.audit.models import AuditEvent
from crm.common.exceptions import DomainError
from crm.conftest import STRONG_PASSWORD
from crm.identity.models import User

pytestmark = pytest.mark.django_db


def _run(monkeypatch: pytest.MonkeyPatch, password: str, *args: str) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(password + "\n"))
    out = io.StringIO()
    call_command(
        "create_first_administrator",
        "--login", "Chief.Admin",
        "--display-name", "Главный администратор",
        "--password-stdin",
        *args,
        stdout=out,
    )  # fmt: skip
    return out.getvalue()


def test_command_creates_administrator_and_audits_as_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    output = _run(monkeypatch, STRONG_PASSWORD)

    user = User.objects.get(crm_login="chief.admin")
    assert user.display_name == "Главный администратор"
    assert user.check_password(STRONG_PASSWORD)
    assert user.permissions_version == 2
    assert services.effective_grants(user) == ADMINISTRATOR_GRANTS
    assert STRONG_PASSWORD not in output

    events = list(AuditEvent.objects.order_by("occurred_at", "id"))
    assert [e.action for e in events] == ["user.created", "role.assigned"]
    for event in events:
        assert event.actor_type == "cli"
        assert event.actor is None
        assert event.actor_label.startswith("os:")
        assert event.entity_id == str(user.pk)
        assert STRONG_PASSWORD not in str(event.metadata)


def test_command_refuses_when_an_active_administrator_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _run(monkeypatch, STRONG_PASSWORD)
    events = AuditEvent.objects.count()

    with pytest.raises(CommandError, match="already exists"):
        _run(monkeypatch, "a-different-long-password")

    assert User.objects.count() == 1
    assert AuditEvent.objects.count() == events


@pytest.mark.parametrize("password", ["short", "password1234", ""])
def test_command_applies_the_password_policy_and_creates_nothing(
    monkeypatch: pytest.MonkeyPatch, password: str
) -> None:
    with pytest.raises(CommandError):
        _run(monkeypatch, password)

    assert not User.objects.exists()
    assert not UserRole.objects.exists()
    assert not AuditEvent.objects.exists()


def test_password_cannot_be_given_on_the_command_line() -> None:
    with pytest.raises((CommandError, SystemExit, TypeError)):
        call_command(
            "create_first_administrator",
            "--login", "x.admin",
            "--display-name", "X",
            "--password", STRONG_PASSWORD,
        )  # fmt: skip

    assert not User.objects.exists()


def test_service_refuses_invalid_login_atomically() -> None:
    with pytest.raises(DomainError) as error:
        services.create_first_administrator(
            operator="os:tests", crm_login="No Spaces", display_name="A", password=STRONG_PASSWORD
        )

    assert error.value.code == "invalid_login"
    assert not User.objects.exists()
    assert not AuditEvent.objects.exists()
