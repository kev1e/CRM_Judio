"""Sign-in domain service: Q13 (approval in Telegram, single use, 3 minutes,
progressive throttling, 12-hour sessions) and Q30 (the CRM login, never the
Telegram username, identifies the account)."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.conftest import STRONG_PASSWORD, Employee, EmployeeFactory, UserFactory
from crm.identity import auth, sessions, throttling
from crm.identity import services as identity
from crm.identity.auth import LoginState
from crm.identity.models import (
    ChallengeDelivery,
    LoginChallenge,
    LoginChallengeStatus,
    Session,
    ThrottleKind,
    User,
)
from crm.identity.throttling import POLICIES, Subject
from crm.telegram.fake import FakeGateway
from crm.telegram.gateway import TelegramRefusedError, TelegramUnavailableError

pytestmark = pytest.mark.django_db

IP = "203.0.113.5"
AGENT = "Mozilla/5.0 (tests)"


def start(employee: Employee, *, password: str | None = None, ip: str = IP) -> auth.StartedLogin:
    return auth.start_login(
        crm_login=employee.user.crm_login,
        password=employee.password if password is None else password,
        ip_address=ip,
        user_agent=AGENT,
    )


def complete(started: auth.StartedLogin, *, key: str | None = None) -> auth.LoginProgress:
    return auth.complete_login(
        challenge_id=started.challenge_id,
        attempt_key=started.attempt_key if key is None else key,
        ip_address=IP,
        user_agent=AGENT,
    )


def approve(started: auth.StartedLogin, employee: Employee) -> auth.Decision:
    return auth.decide_challenge(
        challenge_id=started.challenge_id,
        telegram_user_id=employee.telegram_user_id,
        approve=True,
    )


def sign_in(employee: Employee) -> auth.LoginProgress:
    started = start(employee)
    approve(started, employee)
    return complete(started)


def age(challenge_id: UUID, seconds: int) -> None:
    """Make the challenge look as if it was created `seconds` ago."""
    challenge = LoginChallenge.objects.get(pk=challenge_id)
    LoginChallenge.objects.filter(pk=challenge_id).update(
        created_at=challenge.created_at - timedelta(seconds=seconds),
        expires_at=challenge.expires_at - timedelta(seconds=seconds),
    )


def reasons(action: str) -> list[str]:
    return [
        event.metadata["reason"]
        for event in AuditEvent.objects.filter(action=action).order_by("occurred_at", "id")
    ]


# --- Password step ----------------------------------------------------------


def test_correct_password_opens_a_three_minute_challenge(employee: Employee) -> None:
    before = timezone.now()

    started = start(employee)

    challenge = LoginChallenge.objects.get(pk=started.challenge_id)
    assert challenge.user == employee.user
    assert challenge.status == LoginChallengeStatus.PENDING
    assert challenge.telegram_user_id == employee.telegram_user_id
    assert challenge.expires_at - challenge.created_at == timedelta(seconds=180)
    assert challenge.created_at >= before
    assert challenge.ip_address == IP
    assert not Session.objects.exists()


def test_the_attempt_key_is_stored_only_as_a_hash(employee: Employee) -> None:
    started = start(employee)

    challenge = LoginChallenge.objects.get(pk=started.challenge_id)
    assert started.attempt_key not in challenge.attempt_key_hash
    assert challenge.attempt_key_hash == sessions.hash_token(started.attempt_key)
    assert started.attempt_key not in repr(started)
    assert started.attempt_key not in str(list(AuditEvent.objects.values()))


def test_login_is_case_insensitive_and_trimmed(employee: Employee) -> None:
    started = auth.start_login(
        crm_login="  Anna.Petrova ", password=employee.password, ip_address=IP, user_agent=AGENT
    )

    assert LoginChallenge.objects.get(pk=started.challenge_id).user == employee.user


@pytest.mark.parametrize("password", ["wrong-password-123", "", "x" * 5000])
def test_wrong_password_is_refused_with_the_generic_error(
    employee: Employee, password: str
) -> None:
    with pytest.raises(auth.InvalidCredentialsError):
        start(employee, password=password)

    assert not LoginChallenge.objects.exists()
    assert reasons("auth.login_failed") == ["bad_password"]


def test_unknown_login_gets_the_same_error_and_is_not_written_down(db: None) -> None:
    with pytest.raises(auth.InvalidCredentialsError) as error:
        auth.start_login(
            crm_login="hunter2-my-password", password="whatever", ip_address=IP, user_agent=AGENT
        )

    assert error.value.code == "invalid_credentials"
    event = AuditEvent.objects.get(action="auth.login_failed")
    assert event.metadata == {"reason": "unknown_login", "ip_address": IP}
    assert event.entity_type == "source"
    assert "hunter2" not in str(AuditEvent.objects.values())


def test_account_without_a_password_cannot_sign_in(make_user: UserFactory) -> None:
    user = make_user("no.password")

    with pytest.raises(auth.InvalidCredentialsError):
        auth.start_login(crm_login=user.crm_login, password="", ip_address=IP, user_agent=AGENT)


def test_deactivated_account_gets_the_generic_error(employee: Employee) -> None:
    User.objects.filter(pk=employee.user.pk).update(is_active=False, deactivated_at=timezone.now())

    with pytest.raises(auth.InvalidCredentialsError):
        start(employee)

    assert reasons("auth.login_failed") == ["user_inactive"]
    assert not LoginChallenge.objects.exists()


def test_account_without_telegram_cannot_sign_in(make_user: UserFactory) -> None:
    user = make_user("not.bound", password=STRONG_PASSWORD)

    with pytest.raises(auth.TelegramNotBoundError):
        auth.start_login(
            crm_login=user.crm_login, password=STRONG_PASSWORD, ip_address=IP, user_agent=AGENT
        )

    assert not LoginChallenge.objects.exists()


def test_telegram_binding_state_is_not_revealed_without_the_password(
    make_user: UserFactory,
) -> None:
    user = make_user("not.bound", password=STRONG_PASSWORD)

    with pytest.raises(auth.InvalidCredentialsError):
        auth.start_login(
            crm_login=user.crm_login, password="wrong-password-123", ip_address=IP, user_agent=AGENT
        )


def test_telegram_username_is_not_a_login(employee: Employee) -> None:
    User.objects.filter(pk=employee.user.pk).update(telegram_username="anna_tg")

    with pytest.raises(auth.InvalidCredentialsError):
        auth.start_login(
            crm_login="anna_tg", password=employee.password, ip_address=IP, user_agent=AGENT
        )


def test_new_attempt_cancels_the_previous_one(employee: Employee) -> None:
    first = start(employee)
    second = start(employee)

    assert LoginChallenge.objects.get(pk=first.challenge_id).status == "cancelled"
    assert complete(first).state is LoginState.INVALID
    with pytest.raises(auth.ChallengeRejectedError):
        approve(first, employee)
    assert approve(second, employee) is auth.Decision.APPROVED


def test_database_allows_one_pending_challenge_per_user(employee: Employee) -> None:
    started = start(employee)
    challenge = LoginChallenge.objects.get(pk=started.challenge_id)

    with pytest.raises(IntegrityError), transaction.atomic():
        LoginChallenge.objects.create(
            user=employee.user,
            telegram_user_id=employee.telegram_user_id,
            attempt_key_hash="0" * 64,
            created_at=challenge.created_at,
            expires_at=challenge.expires_at,
        )


def test_database_refuses_a_challenge_longer_than_180_seconds(employee: Employee) -> None:
    now = timezone.now()

    with pytest.raises(IntegrityError), transaction.atomic():
        LoginChallenge.objects.create(
            user=employee.user,
            telegram_user_id=employee.telegram_user_id,
            attempt_key_hash="1" * 64,
            created_at=now,
            expires_at=now + timedelta(seconds=181),
        )


# --- Decision in Telegram ---------------------------------------------------


def test_approval_from_the_bound_account_is_accepted(employee: Employee) -> None:
    started = start(employee)

    assert approve(started, employee) is auth.Decision.APPROVED

    challenge = LoginChallenge.objects.get(pk=started.challenge_id)
    assert challenge.status == LoginChallengeStatus.APPROVED
    assert challenge.decided_at is not None
    event = AuditEvent.objects.get(action="auth.challenge_approved")
    assert event.actor == employee.user
    # Approval alone opens nothing: the browser still has to collect the session.
    assert not Session.objects.exists()


def test_denial_ends_the_attempt(employee: Employee) -> None:
    started = start(employee)

    decision = auth.decide_challenge(
        challenge_id=started.challenge_id,
        telegram_user_id=employee.telegram_user_id,
        approve=False,
    )

    assert decision is auth.Decision.DENIED
    assert complete(started).state is LoginState.DENIED
    assert AuditEvent.objects.filter(action="auth.challenge_denied").exists()
    assert not Session.objects.exists()


def test_another_telegram_account_cannot_approve(
    employee: Employee, make_employee: EmployeeFactory
) -> None:
    colleague = make_employee("boris.ivanov")
    started = start(employee)

    for foreign_id in (colleague.telegram_user_id, 999_999_999):
        with pytest.raises(auth.ChallengeRejectedError) as error:
            auth.decide_challenge(
                challenge_id=started.challenge_id, telegram_user_id=foreign_id, approve=True
            )
        assert error.value.code == "challenge_rejected"

    assert LoginChallenge.objects.get(pk=started.challenge_id).status == "pending"
    assert reasons("auth.challenge_decision_rejected") == ["foreign_telegram_account"] * 2
    assert complete(started).state is LoginState.PENDING


def test_decision_cannot_be_changed_or_repeated(employee: Employee) -> None:
    started = start(employee)
    approve(started, employee)

    with pytest.raises(auth.ChallengeRejectedError):
        approve(started, employee)
    with pytest.raises(auth.ChallengeRejectedError):
        auth.decide_challenge(
            challenge_id=started.challenge_id,
            telegram_user_id=employee.telegram_user_id,
            approve=False,
        )

    assert LoginChallenge.objects.get(pk=started.challenge_id).status == "approved"
    assert reasons("auth.challenge_decision_rejected") == ["already_approved"] * 2


def test_expired_challenge_cannot_be_approved(employee: Employee) -> None:
    started = start(employee)
    age(started.challenge_id, 181)

    with pytest.raises(auth.ChallengeRejectedError):
        approve(started, employee)

    assert reasons("auth.challenge_decision_rejected") == ["expired"]
    assert complete(started).state is LoginState.EXPIRED


def test_unknown_challenge_is_rejected(employee: Employee) -> None:
    with pytest.raises(auth.ChallengeRejectedError):
        auth.decide_challenge(
            challenge_id=uuid4(), telegram_user_id=employee.telegram_user_id, approve=True
        )

    assert reasons("auth.challenge_decision_rejected") == ["unknown_challenge"]


def test_old_telegram_account_cannot_approve_after_the_binding_changed(
    employee: Employee,
) -> None:
    # Q12: after a re-binding the previous Telegram account must be powerless.
    started = start(employee)
    User.objects.filter(pk=employee.user.pk).update(telegram_user_id=555_000_111)

    with pytest.raises(auth.ChallengeRejectedError):
        approve(started, employee)
    with pytest.raises(auth.ChallengeRejectedError):
        auth.decide_challenge(
            challenge_id=started.challenge_id, telegram_user_id=555_000_111, approve=True
        )

    assert reasons("auth.challenge_decision_rejected") == [
        "binding_changed",
        "foreign_telegram_account",
    ]


def test_deactivated_user_cannot_approve(employee: Employee) -> None:
    started = start(employee)
    User.objects.filter(pk=employee.user.pk).update(is_active=False, deactivated_at=timezone.now())

    with pytest.raises(auth.ChallengeRejectedError):
        approve(started, employee)


@pytest.mark.parametrize("bad_id", [0, -5, True, "700001"])
def test_decision_needs_a_real_telegram_id(employee: Employee, bad_id: object) -> None:
    started = start(employee)

    with pytest.raises(ValueError, match="telegram_user_id"):
        auth.decide_challenge(
            challenge_id=started.challenge_id,
            telegram_user_id=bad_id,  # type: ignore[arg-type]
            approve=True,
        )


# --- Collecting the session -------------------------------------------------


def test_pending_attempt_reports_pending(employee: Employee) -> None:
    started = start(employee)

    progress = complete(started)

    assert progress.state is LoginState.PENDING
    assert progress.delivery is ChallengeDelivery.PENDING
    assert progress.session is None


def test_approved_attempt_opens_a_twelve_hour_session(employee: Employee) -> None:
    progress = sign_in(employee)

    assert progress.state is LoginState.AUTHENTICATED
    session = Session.objects.get()
    assert progress.session == session
    assert session.user == employee.user
    assert session.expires_at - session.created_at == timedelta(hours=12)
    assert progress.session_key is not None
    assert session.token_hash == sessions.hash_token(progress.session_key)
    assert progress.session_key not in session.token_hash
    assert progress.session_key not in repr(progress)
    employee.user.refresh_from_db()
    assert employee.user.last_login == session.created_at
    assert AuditEvent.objects.filter(action="auth.login_succeeded").count() == 1
    assert progress.session_key not in str(list(AuditEvent.objects.values()))


def test_an_approval_is_exchanged_only_once(employee: Employee) -> None:
    started = start(employee)
    approve(started, employee)

    first = complete(started)
    second = complete(started)

    assert first.state is LoginState.AUTHENTICATED
    assert second.state is LoginState.INVALID
    assert second.session_key is None
    assert Session.objects.count() == 1


def test_wrong_attempt_key_gets_nothing_even_after_approval(employee: Employee) -> None:
    started = start(employee)
    approve(started, employee)

    assert complete(started, key="not-the-key").state is LoginState.INVALID
    assert not Session.objects.exists()
    # The rightful browser is not affected by the stranger's try.
    assert complete(started).state is LoginState.AUTHENTICATED


def test_unknown_attempt_is_invalid(db: None) -> None:
    progress = auth.complete_login(
        challenge_id=uuid4(), attempt_key="anything", ip_address=IP, user_agent=AGENT
    )

    assert progress.state is LoginState.INVALID


def test_approval_expires_with_the_challenge(employee: Employee) -> None:
    started = start(employee)
    approve(started, employee)
    age(started.challenge_id, 181)

    assert complete(started).state is LoginState.EXPIRED
    assert not Session.objects.exists()


def test_approved_attempt_is_void_when_the_account_is_deactivated(employee: Employee) -> None:
    started = start(employee)
    approve(started, employee)
    User.objects.filter(pk=employee.user.pk).update(is_active=False, deactivated_at=timezone.now())

    assert complete(started).state is LoginState.INVALID
    assert not Session.objects.exists()


def test_database_refuses_a_session_longer_than_twelve_hours(employee: Employee) -> None:
    session = sign_in(employee).session
    assert session is not None

    with pytest.raises(IntegrityError), transaction.atomic():
        Session.objects.filter(pk=session.pk).update(
            expires_at=session.created_at + timedelta(hours=12, seconds=1)
        )


def test_database_refuses_a_second_session_for_one_challenge(employee: Employee) -> None:
    session = sign_in(employee).session
    assert session is not None

    with pytest.raises(IntegrityError), transaction.atomic():
        Session.objects.create(
            user=employee.user,
            challenge=session.challenge,
            token_hash="2" * 64,
            permissions_version=1,
            created_at=session.created_at,
            expires_at=session.expires_at,
        )


# --- Sessions ---------------------------------------------------------------


def test_session_token_authenticates(employee: Employee) -> None:
    progress = sign_in(employee)
    assert progress.session_key is not None

    assert sessions.authenticate(progress.session_key) == progress.session
    assert sessions.authenticate(progress.session_key + "x") is None
    assert sessions.authenticate("") is None


def test_session_ends_after_twelve_hours_even_if_used(employee: Employee) -> None:
    progress = sign_in(employee)
    assert progress.session_key is not None
    assert progress.session is not None
    almost = timedelta(hours=11, minutes=59)
    Session.objects.filter(pk=progress.session.pk).update(
        created_at=progress.session.created_at - almost,
        expires_at=progress.session.expires_at - almost,
    )
    # Using the session does not prolong it.
    assert sessions.authenticate(progress.session_key) is not None
    assert Session.objects.get().expires_at == progress.session.expires_at - almost

    Session.objects.filter(pk=progress.session.pk).update(
        created_at=progress.session.created_at - timedelta(hours=12, seconds=1),
        expires_at=progress.session.expires_at - timedelta(hours=12, seconds=1),
    )
    assert sessions.authenticate(progress.session_key) is None


def test_deactivation_ends_the_session_at_once(employee: Employee) -> None:
    progress = sign_in(employee)
    assert progress.session_key is not None

    User.objects.filter(pk=employee.user.pk).update(is_active=False, deactivated_at=timezone.now())

    assert sessions.authenticate(progress.session_key) is None


def test_revoked_session_stops_working_and_is_audited(employee: Employee) -> None:
    progress = sign_in(employee)
    assert progress.session_key is not None
    assert progress.session is not None
    actor = Actor.for_user(employee.user)

    assert sessions.revoke(actor=actor, session=progress.session, reason="logout") is True
    assert sessions.revoke(actor=actor, session=progress.session, reason="logout") is False

    assert sessions.authenticate(progress.session_key) is None
    assert AuditEvent.objects.filter(action="session.revoked").count() == 1


def test_password_change_ends_sessions_and_waiting_attempts(employee: Employee) -> None:
    progress = sign_in(employee)
    assert progress.session_key is not None
    waiting = start(employee)
    approve(waiting, employee)

    identity.set_password(
        actor=Actor.system("tests"), user=employee.user, raw_password="violet-harbor-lamp-88"
    )

    assert sessions.authenticate(progress.session_key) is None
    assert complete(waiting).state is LoginState.INVALID
    event = AuditEvent.objects.get(action="session.revoked_all")
    assert event.metadata == {"reason": "password_changed", "sessions": 1, "challenges": 1}


def test_other_users_sessions_survive(employee: Employee, make_employee: EmployeeFactory) -> None:
    colleague = make_employee("boris.ivanov")
    colleague_progress = sign_in(colleague)
    assert colleague_progress.session_key is not None
    sign_in(employee)

    identity.set_password(
        actor=Actor.system("tests"), user=employee.user, raw_password="violet-harbor-lamp-88"
    )

    assert sessions.authenticate(colleague_progress.session_key) is not None


# --- Throttling (Q13) -------------------------------------------------------


def fail(employee: Employee, times: int, ip: str = IP) -> None:
    for _ in range(times):
        with pytest.raises(auth.InvalidCredentialsError):
            start(employee, password="wrong-password-123", ip=ip)


def test_repeated_wrong_passwords_are_delayed_progressively(employee: Employee) -> None:
    free = POLICIES[ThrottleKind.LOGIN_AND_SOURCE].free_failures
    fail(employee, free)

    with pytest.raises(auth.InvalidCredentialsError):
        start(employee, password="wrong-password-123")
    with pytest.raises(auth.ThrottledError) as first:
        start(employee, password="wrong-password-123")

    assert 0 < first.value.retry_after <= 6


def test_correct_password_is_also_delayed_while_throttled(employee: Employee) -> None:
    fail(employee, POLICIES[ThrottleKind.LOGIN_AND_SOURCE].free_failures + 1)

    with pytest.raises(auth.ThrottledError):
        start(employee)

    assert not LoginChallenge.objects.exists()


def test_throttle_is_never_permanent(employee: Employee) -> None:
    subject = Subject(ThrottleKind.LOGIN_AND_SOURCE, f"{employee.user.crm_login}|{IP}")
    for _ in range(40):
        throttling.register_failure([subject])
    cap = POLICIES[ThrottleKind.LOGIN_AND_SOURCE].cap_seconds

    wait = throttling.retry_after([subject])
    assert 0 < wait <= cap + 1
    later = timezone.now() + timedelta(seconds=cap + 1)
    assert throttling.retry_after([subject], now=later) == 0


def test_unknown_logins_are_throttled_like_real_ones(db: None) -> None:
    # No enumeration: a login that does not exist behaves exactly like one that does.
    free = POLICIES[ThrottleKind.LOGIN_AND_SOURCE].free_failures
    outcomes = []
    for _ in range(free + 2):
        try:
            auth.start_login(
                crm_login="ghost", password="wrong-password-123", ip_address=IP, user_agent=AGENT
            )
        except DomainError as exc:
            outcomes.append(exc.code)

    assert outcomes == ["invalid_credentials"] * (free + 1) + ["throttled"]


def test_changing_the_address_does_not_give_unlimited_guesses(employee: Employee) -> None:
    per_login = POLICIES[ThrottleKind.LOGIN].free_failures
    for attempt in range(per_login + 1):
        fail(employee, 1, ip=f"198.51.100.{attempt + 1}")

    with pytest.raises(auth.ThrottledError):
        start(employee, password="wrong-password-123", ip="198.51.100.250")


def test_a_stranger_failing_from_elsewhere_does_not_block_the_owner_quickly(
    employee: Employee,
) -> None:
    # Abuse of somebody else's login: a handful of failures from another address
    # must not delay the owner at their own address.
    fail(employee, POLICIES[ThrottleKind.LOGIN_AND_SOURCE].free_failures + 1, ip="198.51.100.77")

    started = start(employee, ip=IP)

    assert LoginChallenge.objects.filter(pk=started.challenge_id).exists()


def test_one_address_trying_many_logins_is_delayed(db: None) -> None:
    per_source = POLICIES[ThrottleKind.SOURCE].free_failures
    for attempt in range(per_source + 1):
        with pytest.raises(auth.InvalidCredentialsError):
            auth.start_login(
                crm_login=f"guess{attempt}", password="x", ip_address=IP, user_agent=AGENT
            )

    with pytest.raises(auth.ThrottledError):
        auth.start_login(crm_login="fresh.login", password="x", ip_address=IP, user_agent=AGENT)


def test_success_clears_the_failures_of_that_login(employee: Employee) -> None:
    free = POLICIES[ThrottleKind.LOGIN_AND_SOURCE].free_failures
    fail(employee, free)
    start(employee)

    fail(employee, free)

    start(employee)  # still not throttled: the counter started over


def test_telegram_prompts_are_rate_limited_until_one_is_approved(employee: Employee) -> None:
    # A stolen password must not let anybody flood the owner's Telegram.
    free = POLICIES[ThrottleKind.MFA].free_failures
    for _ in range(free + 1):
        start(employee)

    with pytest.raises(auth.ThrottledError):
        start(employee)

    assert LoginChallenge.objects.count() == free + 1


def test_completed_login_clears_the_prompt_counter(employee: Employee) -> None:
    free = POLICIES[ThrottleKind.MFA].free_failures
    for _ in range(free):
        start(employee)
    sign_in(employee)

    for _ in range(free):
        start(employee)


# --- Delivery of the prompt -------------------------------------------------


def test_prompt_is_sent_to_the_bound_telegram_id(
    employee: Employee, fake_telegram: type[FakeGateway]
) -> None:
    started = start(employee)

    assert auth.deliver_challenge(started.challenge_id) is True

    (prompt,) = fake_telegram.sent
    assert prompt.chat_id == employee.telegram_user_id
    assert prompt.challenge_id == started.challenge_id
    assert prompt.crm_login == "anna.petrova"
    assert prompt.ip_address == IP
    challenge = LoginChallenge.objects.get(pk=started.challenge_id)
    assert challenge.delivery == ChallengeDelivery.SENT
    assert challenge.telegram_message_id is not None
    assert complete(started).delivery is ChallengeDelivery.SENT


def test_prompt_is_enqueued_when_the_attempt_is_committed(
    employee: Employee,
    fake_telegram: type[FakeGateway],
    django_capture_on_commit_callbacks: object,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):  # type: ignore[operator]
        started = start(employee)

    assert [prompt.challenge_id for prompt in fake_telegram.sent] == [started.challenge_id]


def test_delivery_is_not_repeated(employee: Employee, fake_telegram: type[FakeGateway]) -> None:
    started = start(employee)

    auth.deliver_challenge(started.challenge_id)
    assert auth.deliver_challenge(started.challenge_id) is False

    assert len(fake_telegram.sent) == 1


def test_nothing_is_sent_for_a_finished_or_expired_attempt(
    employee: Employee, fake_telegram: type[FakeGateway]
) -> None:
    cancelled = start(employee)
    expired = start(employee)
    age(expired.challenge_id, 181)

    assert auth.deliver_challenge(cancelled.challenge_id) is False
    assert auth.deliver_challenge(expired.challenge_id) is False
    assert auth.deliver_challenge(uuid4()) is False
    assert fake_telegram.sent == []


def test_nothing_is_sent_when_the_binding_changed_after_the_attempt(
    employee: Employee, fake_telegram: type[FakeGateway]
) -> None:
    started = start(employee)
    User.objects.filter(pk=employee.user.pk).update(telegram_user_id=555_000_111)

    assert auth.deliver_challenge(started.challenge_id) is False

    assert fake_telegram.sent == []
    assert LoginChallenge.objects.get(pk=started.challenge_id).delivery == "failed"


def test_refusal_by_telegram_fails_the_delivery(
    employee: Employee, fake_telegram: type[FakeGateway]
) -> None:
    fake_telegram.failure = TelegramRefusedError("TelegramForbiddenError")
    started = start(employee)

    assert auth.deliver_challenge(started.challenge_id) is False

    assert complete(started).delivery is ChallengeDelivery.FAILED
    assert reasons("auth.challenge_delivery_failed") == ["telegram_refused"]


def test_telegram_outage_blocks_the_login_but_not_open_sessions(
    employee: Employee, fake_telegram: type[FakeGateway]
) -> None:
    # Q13: a new login fails closed; an existing session keeps working.
    open_session = sign_in(employee)
    assert open_session.session_key is not None
    fake_telegram.failure = TelegramUnavailableError("TelegramNetworkError")
    started = start(employee)

    with pytest.raises(TelegramUnavailableError):
        auth.deliver_challenge(started.challenge_id)
    auth.mark_delivery_failed(started.challenge_id, reason="telegram_unavailable")

    progress = complete(started)
    assert progress.state is LoginState.PENDING
    assert progress.delivery is ChallengeDelivery.FAILED
    assert progress.session is None
    assert sessions.authenticate(open_session.session_key) is not None
