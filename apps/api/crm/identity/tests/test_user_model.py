import pytest
from django.db import DataError, IntegrityError, transaction
from django.utils import timezone

from crm.conftest import UserFactory
from crm.identity.models import User

pytestmark = pytest.mark.django_db


def _expect_integrity_error(**changes: object) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(crm_login="user1").update(**changes)


def test_user_has_time_ordered_uuid_and_defaults(make_user: UserFactory) -> None:
    first, second = make_user(), make_user()

    assert first.pk.version == 7
    assert first.pk < second.pk
    assert first.is_active is True
    assert first.permissions_version == 1
    assert first.telegram_user_id is None
    assert first.email is None
    assert first.email_verified_at is None


@pytest.mark.parametrize("login", ["Upper", "ab", "-lead", "has space", "кириллица", "a" * 65, ""])
def test_database_rejects_malformed_login(login: str) -> None:
    # Over-long values fail the column length (DataError), the rest the format check.
    with pytest.raises((IntegrityError, DataError)), transaction.atomic():
        User.objects.create(crm_login=login, display_name="X")


def test_login_is_unique(make_user: UserFactory) -> None:
    make_user("same.login")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create(crm_login="same.login", display_name="Other")


def test_telegram_id_is_unique_but_many_users_may_have_none(make_user: UserFactory) -> None:
    make_user()
    make_user()
    now = timezone.now()
    User.objects.filter(crm_login="user1").update(telegram_user_id=1001, telegram_bound_at=now)

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(crm_login="user2").update(telegram_user_id=1001, telegram_bound_at=now)


def test_same_telegram_username_on_two_accounts_is_allowed(make_user: UserFactory) -> None:
    # The username is a mutable label, not an identity key (Q30).
    make_user()
    make_user()

    assert User.objects.update(telegram_username="shared_handle") == 2


def test_telegram_id_and_binding_time_go_together(make_user: UserFactory) -> None:
    make_user()

    _expect_integrity_error(telegram_user_id=5)
    _expect_integrity_error(telegram_bound_at=timezone.now())


def test_email_is_unique_when_present_and_stored_lowercase(make_user: UserFactory) -> None:
    make_user(email="one@example.com")
    make_user()

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(crm_login="user2").update(email="one@example.com")
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(crm_login="user2").update(email="Mixed@Example.com")


def test_email_cannot_be_marked_verified_without_an_administrator(make_user: UserFactory) -> None:
    make_user(email="one@example.com")

    _expect_integrity_error(email_verified_at=timezone.now())


def test_verified_state_requires_an_address(make_user: UserFactory) -> None:
    verifier = make_user()
    make_user()

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.filter(crm_login="user2").update(
            email_verified_at=timezone.now(), email_verified_by=verifier
        )


def test_inactive_user_must_have_a_deactivation_time_and_active_must_not(
    make_user: UserFactory,
) -> None:
    make_user()

    _expect_integrity_error(is_active=False)
    _expect_integrity_error(deactivated_at=timezone.now())
