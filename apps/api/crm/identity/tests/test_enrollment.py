"""Q11: first-time Telegram binding with a one-time token."""

import hashlib
import threading
from collections.abc import Callable
from datetime import timedelta

import pytest
from django.conf import settings
from django.db import connection
from django.utils import timezone

from crm.access import services as access
from crm.access.permissions import Scope
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import UserFactory
from crm.identity import enrollment
from crm.identity.models import TelegramEnrollmentToken, User

pytestmark = pytest.mark.django_db

TG_ID = 555000111


def _redeem(raw_token: str, telegram_user_id: object = TG_ID, **overrides: object) -> User:
    params: dict[str, object] = {
        "raw_token": raw_token,
        "telegram_user_id": telegram_user_id,
        "telegram_username": "ivan_p",
        "chat_is_private": True,
    }
    params.update(overrides)
    return enrollment.redeem_token(**params)  # type: ignore[arg-type]


def _rejections() -> list[tuple[str, int]]:
    return [
        (event.metadata["reason"], event.metadata["telegram_user_id"])
        for event in AuditEvent.objects.filter(action="telegram.enrollment_rejected").order_by(
            "occurred_at", "id"
        )
    ]


def _assert_rejected(reason: str, raw_token: str, **overrides: object) -> None:
    with pytest.raises(enrollment.EnrollmentRejectedError) as error:
        _redeem(raw_token, **overrides)
    # One generic outcome for the sender, the real reason only in the audit log.
    assert error.value.code == "enrollment_rejected"
    assert error.value.message == "The binding code is not valid."
    assert error.value.reason == reason
    assert _rejections()[-1][0] == reason


# --- Issuing -----------------------------------------------------------------


def test_administrator_issues_a_token_that_is_stored_only_as_a_hash(
    admin_actor: Actor, administrator: User, make_user: UserFactory
) -> None:
    user = make_user()

    issued = enrollment.issue_token(actor=admin_actor, user=user)

    token = TelegramEnrollmentToken.objects.get(user=user)
    assert len(issued.value) >= 43
    assert token.token_hash == hashlib.sha256(issued.value.encode()).hexdigest()
    assert issued.value not in token.token_hash
    assert token.expires_at == issued.expires_at
    assert timedelta(minutes=29) < issued.expires_at - timezone.now() <= timedelta(minutes=30)
    assert issued.value not in repr(issued)

    event = AuditEvent.objects.get(action="telegram.enrollment_issued", entity_id=str(user.pk))
    assert event.actor == administrator
    assert event.metadata == {"expires_at": issued.expires_at.isoformat(), "replaced_pending": 0}
    assert issued.value not in str(event.metadata)


def test_token_lifetime_follows_the_setting(
    admin_actor: Actor, make_user: UserFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "TELEGRAM_ENROLLMENT_TOKEN_TTL_MINUTES", 5)

    issued = enrollment.issue_token(actor=admin_actor, user=make_user())

    assert timedelta(minutes=4) < issued.expires_at - timezone.now() <= timedelta(minutes=5)


def test_holder_of_user_create_in_a_custom_role_may_issue(
    admin_actor: Actor, make_user: UserFactory
) -> None:
    provisioner = make_user()
    role = access.create_role(actor=admin_actor, key="hr", name="HR")
    access.set_role_grants(actor=admin_actor, role=role, grants={"user.create": Scope.COMPANY})
    access.assign_role(actor=admin_actor, user=provisioner, role=role)

    assert enrollment.issue_token(actor=Actor.for_user(provisioner), user=make_user()).value


@pytest.mark.parametrize("kind", ["no_roles", "department_scope_only", "system", "cli", "self"])
def test_unauthorized_actor_cannot_issue(
    kind: str, admin_actor: Actor, make_user: UserFactory
) -> None:
    target = make_user()
    if kind == "system":
        actor = Actor.system("worker")
    elif kind == "cli":
        actor = Actor.cli("os:someone")
    elif kind == "self":
        actor = Actor.for_user(target)
    else:
        user = make_user()
        if kind == "department_scope_only":
            # A department-scoped grant is not enough until departments exist (S2).
            role = access.create_role(actor=admin_actor, key="lead", name="Lead")
            access.set_role_grants(
                actor=admin_actor, role=role, grants={"user.create": Scope.MANAGED_DEPARTMENTS}
            )
            access.assign_role(actor=admin_actor, user=user, role=role)
        actor = Actor.for_user(user)

    with pytest.raises(PermissionDeniedError):
        enrollment.issue_token(actor=actor, user=target)

    assert not TelegramEnrollmentToken.objects.filter(user=target).exists()
    assert not AuditEvent.objects.filter(
        action="telegram.enrollment_issued", entity_id=str(target.pk)
    ).exists()


def test_issuing_again_revokes_the_previous_token(
    admin_actor: Actor, make_user: UserFactory
) -> None:
    user = make_user()
    first = enrollment.issue_token(actor=admin_actor, user=user)
    second = enrollment.issue_token(actor=admin_actor, user=user)

    assert TelegramEnrollmentToken.objects.filter(user=user, revoked_at__isnull=True).count() == 1
    assert (
        AuditEvent.objects.filter(action="telegram.enrollment_issued")
        .order_by("-occurred_at", "-id")
        .first()
        .metadata["replaced_pending"]  # type: ignore[union-attr]
        == 1
    )
    _assert_rejected("token_revoked", first.value)
    assert _redeem(second.value).pk == user.pk


def test_token_is_not_issued_for_bound_or_deactivated_account(
    admin_actor: Actor, make_user: UserFactory
) -> None:
    bound = make_user()
    _redeem(enrollment.issue_token(actor=admin_actor, user=bound).value)
    inactive = make_user()
    User.objects.filter(pk=inactive.pk).update(is_active=False, deactivated_at=timezone.now())

    for user, code in ((bound, "telegram_already_bound"), (inactive, "user_inactive")):
        with pytest.raises(DomainError) as error:
            enrollment.issue_token(actor=admin_actor, user=user)
        assert error.value.code == code


# --- Redeeming ---------------------------------------------------------------


def test_redeeming_binds_the_numeric_id_and_consumes_the_token(
    admin_actor: Actor, make_user: UserFactory
) -> None:
    user = make_user()
    issued = enrollment.issue_token(actor=admin_actor, user=user)

    bound = _redeem(issued.value, telegram_username="@Ivan_P")

    user.refresh_from_db()
    assert bound.pk == user.pk
    assert user.telegram_user_id == TG_ID
    assert user.telegram_username == "Ivan_P"
    assert user.telegram_bound_at is not None
    assert TelegramEnrollmentToken.objects.get(user=user).used_at is not None
    event = AuditEvent.objects.get(action="telegram.bound")
    assert (event.actor_type, event.actor_label) == ("system", "telegram-bot")
    assert event.entity_id == str(user.pk)
    assert event.metadata == {"telegram_user_id": TG_ID}


def test_binding_works_for_a_telegram_account_without_username(
    admin_actor: Actor, make_user: UserFactory
) -> None:
    # Q30: the Telegram username is optional and is not the identity.
    user = make_user()

    _redeem(enrollment.issue_token(actor=admin_actor, user=user).value, telegram_username=None)

    user.refresh_from_db()
    assert (user.telegram_user_id, user.telegram_username) == (TG_ID, "")


def test_token_cannot_be_used_twice(admin_actor: Actor, make_user: UserFactory) -> None:
    issued = enrollment.issue_token(actor=admin_actor, user=make_user())
    _redeem(issued.value)

    _assert_rejected("token_used", issued.value)
    _assert_rejected("token_used", issued.value, telegram_user_id=TG_ID + 1)

    assert User.objects.filter(telegram_user_id__isnull=False).count() == 1


def test_expired_token_is_refused(admin_actor: Actor, make_user: UserFactory) -> None:
    user = make_user()
    issued = enrollment.issue_token(actor=admin_actor, user=user)
    TelegramEnrollmentToken.objects.filter(user=user).update(
        expires_at=timezone.now() - timedelta(seconds=1)
    )

    _assert_rejected("token_expired", issued.value)

    user.refresh_from_db()
    assert user.telegram_user_id is None
    assert TelegramEnrollmentToken.objects.get(user=user).used_at is None


@pytest.mark.parametrize(
    "mutate", [lambda t: t[:-1], lambda t: t + "x", lambda t: t.swapcase(), lambda t: ""]
)
def test_altered_or_unknown_token_is_refused(
    mutate: Callable[[str], str], admin_actor: Actor, make_user: UserFactory
) -> None:
    user = make_user()
    issued = enrollment.issue_token(actor=admin_actor, user=user)

    _assert_rejected("unknown_token", mutate(issued.value))

    assert TelegramEnrollmentToken.objects.get(user=user).used_at is None
    assert not User.objects.filter(telegram_user_id__isnull=False).exists()


def test_token_sent_outside_a_private_chat_is_refused_and_stays_valid(
    admin_actor: Actor, make_user: UserFactory
) -> None:
    user = make_user()
    issued = enrollment.issue_token(actor=admin_actor, user=user)

    _assert_rejected("not_private_chat", issued.value, chat_is_private=False)

    assert TelegramEnrollmentToken.objects.get(user=user).used_at is None


def test_telegram_account_already_bound_to_another_user_is_refused(
    admin_actor: Actor, make_user: UserFactory
) -> None:
    first, second = make_user(), make_user()
    _redeem(enrollment.issue_token(actor=admin_actor, user=first).value)
    issued = enrollment.issue_token(actor=admin_actor, user=second)

    _assert_rejected("telegram_account_in_use", issued.value)

    second.refresh_from_db()
    assert second.telegram_user_id is None
    # The refused attempt does not burn the token: the right account can still use it.
    assert _redeem(issued.value, telegram_user_id=TG_ID + 1).pk == second.pk


def test_same_username_cannot_take_over_an_account(
    admin_actor: Actor, make_user: UserFactory
) -> None:
    # Username impersonation: a stranger with the victim's handle and no token gets nothing.
    victim = make_user()
    _redeem(enrollment.issue_token(actor=admin_actor, user=victim).value, telegram_username="boss")

    _assert_rejected(
        "unknown_token", "guessed-token", telegram_user_id=999, telegram_username="boss"
    )

    victim.refresh_from_db()
    assert victim.telegram_user_id == TG_ID


def test_token_of_a_deactivated_account_is_refused(
    admin_actor: Actor, make_user: UserFactory
) -> None:
    user = make_user()
    issued = enrollment.issue_token(actor=admin_actor, user=user)
    User.objects.filter(pk=user.pk).update(is_active=False, deactivated_at=timezone.now())

    _assert_rejected("user_inactive", issued.value)


@pytest.mark.parametrize("bad_id", [0, -5, True, "555", 5.0, None])
def test_telegram_id_must_be_a_positive_integer_from_the_update(bad_id: object) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        _redeem("whatever", telegram_user_id=bad_id)


def test_rejections_never_record_the_token(admin_actor: Actor, make_user: UserFactory) -> None:
    issued = enrollment.issue_token(actor=admin_actor, user=make_user())
    _redeem(issued.value)
    with pytest.raises(enrollment.EnrollmentRejectedError):
        _redeem(issued.value)

    stored = str(list(AuditEvent.objects.values_list("metadata", "entity_id")))
    assert issued.value not in stored


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_two_telegram_accounts_redeeming_one_token_at_once_bind_only_one() -> None:
    from crm.identity import setup

    admin, _ = setup.create_first_administrator(
        operator="os:tests",
        crm_login="root.admin",
        display_name="A",
        password="plum-orbit-candle-73",
    )
    user = User.objects.create(crm_login="racer", display_name="Racer")
    issued = enrollment.issue_token(actor=Actor.for_user(admin), user=user)
    barrier = threading.Barrier(2)
    results: list[object] = [None, None]

    def worker(index: int) -> None:
        try:
            barrier.wait(timeout=10)
            results[index] = _redeem(issued.value, telegram_user_id=TG_ID + index)
        except Exception as exc:
            results[index] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sum(isinstance(r, User) for r in results) == 1, results
    (loser,) = [r for r in results if not isinstance(r, User)]
    assert isinstance(loser, enrollment.EnrollmentRejectedError)
    assert loser.reason == "token_used"
    user.refresh_from_db()
    assert user.telegram_user_id in {TG_ID, TG_ID + 1}
    assert User.objects.filter(telegram_user_id__isnull=False).count() == 1


def test_repeated_wrong_codes_from_one_telegram_account_are_delayed(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    # Q13: progressive delay instead of a lockout; the real code still works later.
    from crm.identity import throttling
    from crm.identity.models import ThrottleKind
    from crm.identity.throttling import POLICIES, Subject

    token = enrollment.issue_token(actor=admin_actor, user=make_user())
    free = POLICIES[ThrottleKind.ENROLLMENT].free_failures
    for _ in range(free + 1):
        _assert_rejected("unknown_token", "guess")

    # Even the right code is refused while the delay lasts, and it is not burnt.
    with pytest.raises(enrollment.EnrollmentRejectedError) as error:
        _redeem(token.value)
    assert error.value.reason == "throttled"
    assert error.value.code == "enrollment_rejected"

    # Another Telegram account is not affected.
    other = enrollment.issue_token(actor=admin_actor, user=make_user())
    assert _redeem(other.value, telegram_user_id=TG_ID + 1).telegram_user_id == TG_ID + 1

    throttling.reset([Subject(ThrottleKind.ENROLLMENT, str(TG_ID))])
    assert _redeem(token.value).telegram_user_id == TG_ID
