"""D036: a new employee chooses their own password through a one-time link that
the bot sends to the Telegram account they have just bound."""

from datetime import timedelta

import pytest
from django.utils import timezone
from pytest_django.fixtures import Settings

from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.conftest import STRONG_PASSWORD, Employee, UserFactory
from crm.identity import auth, enrollment, password_setup
from crm.identity.models import PasswordSetupToken, ThrottleKind, User
from crm.identity.throttling import POLICIES

pytestmark = pytest.mark.django_db

TG_ID = 555000111
IP = "203.0.113.5"


@pytest.fixture
def newcomer(make_user: UserFactory, admin_actor: Actor) -> User:
    """Provisioned without a password, Telegram already bound."""
    user = make_user("new.employee")
    token = enrollment.issue_token(actor=admin_actor, user=user)
    enrollment.redeem_token(
        raw_token=token.value, telegram_user_id=TG_ID, telegram_username=None, chat_is_private=True
    )
    user.refresh_from_db()
    return user


def issue() -> enrollment.IssuedToken:
    token = password_setup.issue_for_telegram_account(telegram_user_id=TG_ID)
    assert token is not None
    return token


def reasons() -> list[str]:
    return [
        event.metadata["reason"]
        for event in AuditEvent.objects.filter(action="password_setup.rejected").order_by(
            "occurred_at", "id"
        )
    ]


def test_link_is_issued_for_a_bound_account_without_a_password(
    newcomer: User, settings: Settings
) -> None:
    token = issue()

    stored = PasswordSetupToken.objects.get()
    assert stored.user == newcomer
    assert token.value not in stored.token_hash
    assert stored.expires_at - timezone.now() <= timedelta(minutes=30)
    # The secret is in the fragment, which browsers do not send to servers.
    assert (
        password_setup.setup_url(token) == f"{settings.WEB_PUBLIC_URL}/set-password#{token.value}"
    )
    assert token.value not in str(list(AuditEvent.objects.values()))


def test_employee_sets_the_password_and_can_then_start_a_login(newcomer: User) -> None:
    token = issue()

    user = password_setup.set_initial_password(
        raw_token=token.value, password=STRONG_PASSWORD, ip_address=IP
    )

    assert user == newcomer
    newcomer.refresh_from_db()
    assert newcomer.check_password(STRONG_PASSWORD)
    # No session is opened here: the normal login with Telegram approval follows.
    assert not newcomer.sessions.exists()
    auth.start_login(
        crm_login="new.employee", password=STRONG_PASSWORD, ip_address=IP, user_agent=""
    )
    assert STRONG_PASSWORD not in str(list(AuditEvent.objects.values()))


def test_link_works_once(newcomer: User) -> None:
    token = issue()
    password_setup.set_initial_password(
        raw_token=token.value, password=STRONG_PASSWORD, ip_address=IP
    )

    with pytest.raises(password_setup.SetupLinkRejectedError):
        password_setup.set_initial_password(
            raw_token=token.value, password="another-strong-phrase-55", ip_address=IP
        )

    newcomer.refresh_from_db()
    assert newcomer.check_password(STRONG_PASSWORD)
    assert reasons() == ["token_used"]


def test_weak_password_is_refused_and_the_link_stays_usable(newcomer: User) -> None:
    token = issue()

    with pytest.raises(DomainError) as error:
        password_setup.set_initial_password(raw_token=token.value, password="short", ip_address=IP)
    assert error.value.code == "invalid_password"

    password_setup.set_initial_password(
        raw_token=token.value, password=STRONG_PASSWORD, ip_address=IP
    )


def test_expired_unknown_and_replaced_links_get_one_answer(newcomer: User) -> None:
    old = issue()
    new = issue()  # replaces the previous link
    PasswordSetupToken.objects.filter(revoked_at__isnull=True).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )

    messages = set()
    for raw in (old.value, new.value, "made-up"):
        with pytest.raises(password_setup.SetupLinkRejectedError) as error:
            password_setup.set_initial_password(
                raw_token=raw, password=STRONG_PASSWORD, ip_address=IP
            )
        messages.add((error.value.code, error.value.message))

    assert len(messages) == 1
    assert reasons() == ["token_revoked", "token_expired", "unknown_token"]
    newcomer.refresh_from_db()
    assert not newcomer.has_usable_password()


def test_no_link_for_an_account_that_already_has_a_password(employee: Employee) -> None:
    # An existing password can never be replaced this way: that is recovery (Q28).
    token = password_setup.issue_for_telegram_account(telegram_user_id=employee.telegram_user_id)

    assert token is None
    assert not PasswordSetupToken.objects.exists()


def test_link_issued_earlier_dies_once_a_password_exists(newcomer: User) -> None:
    token = issue()
    newcomer.set_password(STRONG_PASSWORD)
    newcomer.save()

    with pytest.raises(password_setup.SetupLinkRejectedError):
        password_setup.set_initial_password(
            raw_token=token.value, password="another-strong-phrase-55", ip_address=IP
        )

    assert reasons() == ["password_already_set"]


def test_no_link_for_unknown_or_deactivated_accounts(newcomer: User) -> None:
    assert password_setup.issue_for_telegram_account(telegram_user_id=999) is None

    User.objects.filter(pk=newcomer.pk).update(is_active=False, deactivated_at=timezone.now())
    assert password_setup.issue_for_telegram_account(telegram_user_id=TG_ID) is None


def test_deactivated_account_cannot_use_its_link(newcomer: User) -> None:
    token = issue()
    User.objects.filter(pk=newcomer.pk).update(is_active=False, deactivated_at=timezone.now())

    with pytest.raises(password_setup.SetupLinkRejectedError):
        password_setup.set_initial_password(
            raw_token=token.value, password=STRONG_PASSWORD, ip_address=IP
        )


def test_requesting_links_is_rate_limited(newcomer: User) -> None:
    free = POLICIES[ThrottleKind.SETUP_LINK_ISSUE].free_failures
    for _ in range(free + 1):
        issue()

    assert password_setup.issue_for_telegram_account(telegram_user_id=TG_ID) is None


def test_guessing_links_from_one_address_is_delayed(newcomer: User) -> None:
    token = issue()
    free = POLICIES[ThrottleKind.SETUP_LINK_USE].free_failures
    for attempt in range(free + 1):
        with pytest.raises(password_setup.SetupLinkRejectedError):
            password_setup.set_initial_password(
                raw_token=f"guess-{attempt}", password=STRONG_PASSWORD, ip_address=IP
            )

    with pytest.raises(password_setup.SetupLinkRejectedError) as error:
        password_setup.set_initial_password(
            raw_token=token.value, password=STRONG_PASSWORD, ip_address=IP
        )
    assert error.value.reason == "throttled"
    # From another address the real link still works.
    password_setup.set_initial_password(
        raw_token=token.value, password=STRONG_PASSWORD, ip_address="198.51.100.9"
    )
