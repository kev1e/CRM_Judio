import hashlib
import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from crm.access import services as access
from crm.access.models import UserRole
from crm.access.permissions import ADMINISTRATOR_GRANTS, BASELINE_GRANTS
from crm.audit.models import AuditEvent
from crm.common.exceptions import DomainError
from crm.conftest import STRONG_PASSWORD, UserFactory
from crm.identity import enrollment, setup
from crm.identity.models import TelegramEnrollmentToken, User

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
    assert access.effective_grants(user) == {**BASELINE_GRANTS, **ADMINISTRATOR_GRANTS}
    assert STRONG_PASSWORD not in output

    events = list(AuditEvent.objects.order_by("occurred_at", "id"))
    assert [e.action for e in events] == [
        "user.created",
        "role.assigned",
        "telegram.enrollment_issued",
    ]
    for event in events:
        assert event.actor_type == "cli"
        assert event.actor is None
        assert event.actor_label.startswith("os:")
        assert event.entity_id == str(user.pk)
        assert STRONG_PASSWORD not in str(event.metadata)


def test_command_prints_a_binding_code_that_is_stored_only_as_a_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = _run(monkeypatch, STRONG_PASSWORD)

    (line,) = [ln for ln in output.splitlines() if ln.startswith("  /start ")]
    code = line.removeprefix("  /start ")
    token = TelegramEnrollmentToken.objects.get()
    assert token.token_hash == hashlib.sha256(code.encode()).hexdigest()
    assert code not in token.token_hash
    assert code not in str(list(AuditEvent.objects.values_list("metadata", flat=True)))

    bound = enrollment.redeem_token(
        raw_token=code, telegram_user_id=700100, telegram_username="chief", chat_is_private=True
    )
    assert bound.crm_login == "chief.admin"


def test_new_code_can_be_issued_from_cli_only_until_an_administrator_is_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_output = _run(monkeypatch, STRONG_PASSWORD)
    first_code = next(
        ln for ln in first_output.splitlines() if ln.startswith("  /start ")
    ).removeprefix("  /start ")

    out = io.StringIO()
    call_command("issue_first_administrator_token", "--login", "Chief.Admin", stdout=out)
    second_code = next(
        ln for ln in out.getvalue().splitlines() if ln.startswith("  /start ")
    ).removeprefix("  /start ")

    # The new code replaces the old one.
    assert second_code != first_code
    with pytest.raises(enrollment.EnrollmentRejectedError):
        enrollment.redeem_token(
            raw_token=first_code,
            telegram_user_id=700100,
            telegram_username=None,
            chat_is_private=True,
        )
    enrollment.redeem_token(
        raw_token=second_code, telegram_user_id=700100, telegram_username=None, chat_is_private=True
    )

    # Setup is over: an administrator can sign in, the CLI path is closed.
    with pytest.raises(CommandError, match="can already sign in"):
        call_command("issue_first_administrator_token", "--login", "chief.admin")


def test_cli_code_is_issued_only_for_an_administrator(
    monkeypatch: pytest.MonkeyPatch, make_user: UserFactory
) -> None:
    _run(monkeypatch, STRONG_PASSWORD)
    make_user("plain.user")
    issued_before = TelegramEnrollmentToken.objects.count()

    for login in ("plain.user", "nobody.here"):
        with pytest.raises(CommandError, match="No active administrator"):
            call_command("issue_first_administrator_token", "--login", login)

    assert TelegramEnrollmentToken.objects.count() == issued_before


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
        setup.create_first_administrator(
            operator="os:tests", crm_login="No Spaces", display_name="A", password=STRONG_PASSWORD
        )

    assert error.value.code == "invalid_login"
    assert not User.objects.exists()
    assert not AuditEvent.objects.exists()
