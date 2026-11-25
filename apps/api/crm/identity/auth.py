"""Signing in (Q13, Q30): CRM login + password, then approval in Telegram.

    start_login      password check -> a 180-second challenge, delivered by the bot
    decide_challenge the owner of the bound Telegram account approves or denies
    complete_login   the browser that started the attempt exchanges the approval
                     for a session, exactly once

Nothing here trusts the Telegram username, and a callback proves nothing by
itself: a decision counts only when it comes from the numeric Telegram ID that
was bound to the account when the attempt started and still is.

Callers get deliberately poor answers ("invalid credentials", "not valid"); the
real reason of every refusal goes to the audit log only.
"""

import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.utils import timezone

from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity import throttling
from crm.identity.models import (
    ChallengeDelivery,
    LoginChallenge,
    LoginChallengeStatus,
    Session,
    ThrottleKind,
    User,
)
from crm.identity.services import MAX_PASSWORD_LENGTH
from crm.identity.sessions import SESSION_LIFETIME, hash_token
from crm.identity.throttling import Subject

logger = logging.getLogger(__name__)

# Q13: the approval request lives for 3 minutes.
CHALLENGE_LIFETIME = timedelta(seconds=180)

AUTH_ACTOR = Actor.system("auth")
_USER_AGENT_MAX = 256
_LOGIN_MAX = 64
# Verified when the login is unknown or has no password, so that such attempts
# cost the same time as a wrong password for a real account.
_DUMMY_PASSWORD_HASH = make_password(secrets.token_urlsafe(32))


class InvalidCredentialsError(DomainError):
    def __init__(self) -> None:
        super().__init__("invalid_credentials", "The login or password is not correct.")


class ThrottledError(DomainError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("throttled", "Too many attempts. Try again later.")
        self.retry_after = retry_after


class TelegramNotBoundError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "telegram_not_bound",
            "The account is not bound to Telegram yet. Ask an administrator for a binding code.",
        )


class ChallengeRejectedError(DomainError):
    """The decision was not accepted. One generic outcome; the reason is audited."""

    def __init__(self, reason: str) -> None:
        super().__init__("challenge_rejected", "The login request is not valid.")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class StartedLogin:
    """Returned once to the browser that sent the password. `attempt_key` is never
    stored or logged."""

    challenge_id: UUID
    attempt_key: str
    expires_at: datetime

    def __repr__(self) -> str:
        return f"StartedLogin(challenge_id={self.challenge_id})"


class LoginState(StrEnum):
    PENDING = "pending"
    DENIED = "denied"
    EXPIRED = "expired"
    # Unknown attempt, wrong key, already used, cancelled: indistinguishable on purpose.
    INVALID = "invalid"
    AUTHENTICATED = "authenticated"


@dataclass(frozen=True, slots=True)
class LoginProgress:
    state: LoginState
    delivery: ChallengeDelivery | None = None
    session: Session | None = None
    # The browser's session token; present only together with `session`.
    session_key: str | None = None

    def __repr__(self) -> str:
        return f"LoginProgress(state={self.state.value})"


class Decision(StrEnum):
    APPROVED = "approved"
    DENIED = "denied"


def _clean_user_agent(raw: str | None) -> str:
    return "".join(ch for ch in (raw or "") if ch.isprintable())[:_USER_AGENT_MAX]


def _login_subjects(login: str, ip_address: str | None) -> list[Subject]:
    source = ip_address or "unknown"
    return [
        Subject(ThrottleKind.LOGIN_AND_SOURCE, f"{login}|{source}"),
        Subject(ThrottleKind.LOGIN, login),
        Subject(ThrottleKind.SOURCE, source),
    ]


def _refuse_credentials(
    *, reason: str, subjects: list[Subject], user: User | None, ip_address: str | None
) -> InvalidCredentialsError:
    throttling.register_failure(subjects)
    # The typed login is not recorded when no account matches: people type
    # passwords into the wrong field.
    audit.record(
        actor=AUTH_ACTOR,
        action="auth.login_failed",
        entity_type="user" if user else "source",
        entity_id=str(user.pk) if user else (ip_address or "unknown"),
        metadata={"reason": reason, "ip_address": ip_address},
    )
    return InvalidCredentialsError()


def start_login(
    *, crm_login: str, password: str, ip_address: str | None, user_agent: str | None
) -> StartedLogin:
    """Check the password and open a challenge for approval in Telegram."""
    login = crm_login.strip().lower()[:_LOGIN_MAX]
    subjects = _login_subjects(login, ip_address)
    if wait := throttling.retry_after(subjects):
        raise ThrottledError(wait)

    user = User.objects.filter(crm_login=login).first()
    if len(password) > MAX_PASSWORD_LENGTH:
        password_ok = False
    elif user is None or not user.has_usable_password():
        check_password(password, _DUMMY_PASSWORD_HASH)
        password_ok = False
    else:
        password_ok = user.check_password(password)

    if user is None:
        raise _refuse_credentials(
            reason="unknown_login", subjects=subjects, user=None, ip_address=ip_address
        )
    if not password_ok:
        raise _refuse_credentials(
            reason="bad_password", subjects=subjects, user=user, ip_address=ip_address
        )
    if not user.is_active:
        # Same answer as a wrong password: whether an account is deactivated is not public.
        raise _refuse_credentials(
            reason="user_inactive", subjects=subjects, user=user, ip_address=ip_address
        )

    # The password was right: this login from this address is not guessing.
    throttling.reset(subjects[:2])

    if user.telegram_user_id is None:
        audit.record(
            actor=AUTH_ACTOR,
            action="auth.login_failed",
            entity_type="user",
            entity_id=str(user.pk),
            metadata={"reason": "telegram_not_bound", "ip_address": ip_address},
        )
        raise TelegramNotBoundError

    # Each prompt counts until one is approved, so a stolen password cannot be
    # used to flood the owner's Telegram.
    mfa_subject = Subject(ThrottleKind.MFA, str(user.pk))
    if wait := throttling.retry_after([mfa_subject]):
        raise ThrottledError(wait)
    throttling.register_failure([mfa_subject])

    attempt_key = secrets.token_urlsafe(32)
    now = timezone.now()
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        if not locked.is_active or locked.telegram_user_id is None:
            raise InvalidCredentialsError
        # One live prompt per account: a new attempt replaces the previous one.
        LoginChallenge.objects.filter(
            user=locked, status__in=[LoginChallengeStatus.PENDING, LoginChallengeStatus.APPROVED]
        ).update(status=LoginChallengeStatus.CANCELLED)
        challenge = LoginChallenge.objects.create(
            user=locked,
            telegram_user_id=locked.telegram_user_id,
            attempt_key_hash=hash_token(attempt_key),
            ip_address=ip_address,
            user_agent=_clean_user_agent(user_agent),
            created_at=now,
            expires_at=now + CHALLENGE_LIFETIME,
        )
        audit.record(
            actor=AUTH_ACTOR,
            action="auth.challenge_created",
            entity_type="user",
            entity_id=str(locked.pk),
            metadata={"challenge_id": str(challenge.pk), "ip_address": ip_address},
        )
        transaction.on_commit(lambda: _enqueue_delivery(challenge.pk))
    return StartedLogin(
        challenge_id=challenge.pk, attempt_key=attempt_key, expires_at=challenge.expires_at
    )


def _enqueue_delivery(challenge_id: UUID) -> None:
    from crm.identity.tasks import deliver_login_challenge

    try:
        deliver_login_challenge.delay(str(challenge_id))
    except Exception:
        # The queue is down: the prompt cannot be sent, so this login fails closed.
        logger.exception("Could not enqueue the login prompt for challenge %s", challenge_id)
        mark_delivery_failed(challenge_id, reason="queue_unavailable")


def mark_delivery_failed(challenge_id: UUID, *, reason: str) -> None:
    with transaction.atomic():
        changed = LoginChallenge.objects.filter(
            pk=challenge_id, delivery=ChallengeDelivery.PENDING
        ).update(delivery=ChallengeDelivery.FAILED)
        if changed:
            challenge = LoginChallenge.objects.get(pk=challenge_id)
            audit.record(
                actor=AUTH_ACTOR,
                action="auth.challenge_delivery_failed",
                entity_type="user",
                entity_id=str(challenge.user_id),
                metadata={"challenge_id": str(challenge_id), "reason": reason},
            )


def deliver_challenge(challenge_id: UUID) -> bool:
    """Send the approve/deny prompt to the bound Telegram account.

    Called by the worker. Safe to repeat: a challenge that is no longer waiting,
    or whose prompt was already sent, is skipped. Returns True when a prompt was
    sent. Raises `TelegramUnavailableError` for a failure worth retrying.
    """
    from crm.telegram import gateway

    challenge = LoginChallenge.objects.select_related("user").filter(pk=challenge_id).first()
    if (
        challenge is None
        or challenge.status != LoginChallengeStatus.PENDING
        or challenge.delivery != ChallengeDelivery.PENDING
        or challenge.expires_at <= timezone.now()
    ):
        return False
    user = challenge.user
    # Rights and bindings are re-read at send time; the queue message proves nothing.
    if not user.is_active or user.telegram_user_id != challenge.telegram_user_id:
        mark_delivery_failed(challenge.pk, reason="binding_changed")
        return False

    try:
        message_id = gateway.get_gateway().send_login_prompt(
            gateway.LoginPrompt(
                chat_id=challenge.telegram_user_id,
                challenge_id=challenge.pk,
                crm_login=user.crm_login,
                ip_address=challenge.ip_address,
                user_agent=challenge.user_agent,
                expires_at=challenge.expires_at,
            )
        )
    except gateway.TelegramRefusedError:
        mark_delivery_failed(challenge.pk, reason="telegram_refused")
        return False

    LoginChallenge.objects.filter(pk=challenge.pk, delivery=ChallengeDelivery.PENDING).update(
        delivery=ChallengeDelivery.SENT, telegram_message_id=message_id
    )
    return True


def _reject_decision(
    reason: str, *, telegram_user_id: int, challenge: LoginChallenge | None
) -> ChallengeRejectedError:
    audit.record(
        actor=AUTH_ACTOR,
        action="auth.challenge_decision_rejected",
        entity_type="user" if challenge else "telegram_account",
        entity_id=str(challenge.user_id) if challenge else str(telegram_user_id),
        metadata={
            "reason": reason,
            "telegram_user_id": telegram_user_id,
            "challenge_id": str(challenge.pk) if challenge else None,
        },
    )
    return ChallengeRejectedError(reason)


def decide_challenge(*, challenge_id: UUID, telegram_user_id: int, approve: bool) -> Decision:
    """Record the owner's answer to a login prompt.

    `telegram_user_id` must be the sender of the callback as reported by Telegram.
    """
    if (
        not isinstance(telegram_user_id, int)
        or isinstance(telegram_user_id, bool)
        or telegram_user_id <= 0
    ):
        raise ValueError("telegram_user_id must be a positive integer taken from the update.")

    challenge: LoginChallenge | None = None
    reason: str | None = None
    with transaction.atomic():
        challenge = LoginChallenge.objects.select_for_update().filter(pk=challenge_id).first()
        if challenge is None:
            reason = "unknown_challenge"
        else:
            user = User.objects.select_for_update().get(pk=challenge.user_id)
            now = timezone.now()
            if telegram_user_id != challenge.telegram_user_id:
                reason = "foreign_telegram_account"
            elif user.telegram_user_id != challenge.telegram_user_id:
                reason = "binding_changed"
            elif not user.is_active:
                reason = "user_inactive"
            elif challenge.status != LoginChallengeStatus.PENDING:
                reason = f"already_{challenge.status}"
            elif challenge.expires_at <= now:
                reason = "expired"
            else:
                challenge.status = (
                    LoginChallengeStatus.APPROVED if approve else LoginChallengeStatus.DENIED
                )
                challenge.decided_at = now
                challenge.save(update_fields=["status", "decided_at"])
                audit.record(
                    actor=Actor.for_user(user),
                    action="auth.challenge_approved" if approve else "auth.challenge_denied",
                    entity_type="user",
                    entity_id=str(user.pk),
                    metadata={"challenge_id": str(challenge.pk), "via": "telegram"},
                )
                return Decision.APPROVED if approve else Decision.DENIED

    raise _reject_decision(
        reason or "unknown_challenge", telegram_user_id=telegram_user_id, challenge=challenge
    )


def cancel_login(*, challenge_id: UUID, attempt_key: str) -> bool:
    """The browser that started an attempt gives it up: the prompt in Telegram
    stops working. Returns True if a live attempt was cancelled."""
    with transaction.atomic():
        challenge = LoginChallenge.objects.select_for_update().filter(pk=challenge_id).first()
        if (
            challenge is None
            or not hmac.compare_digest(challenge.attempt_key_hash, hash_token(attempt_key))
            or challenge.status not in (LoginChallengeStatus.PENDING, LoginChallengeStatus.APPROVED)
        ):
            return False
        challenge.status = LoginChallengeStatus.CANCELLED
        challenge.save(update_fields=["status"])
        audit.record(
            actor=AUTH_ACTOR,
            action="auth.challenge_cancelled",
            entity_type="user",
            entity_id=str(challenge.user_id),
            metadata={"challenge_id": str(challenge.pk)},
        )
        return True


def complete_login(
    *, challenge_id: UUID, attempt_key: str, ip_address: str | None, user_agent: str | None
) -> LoginProgress:
    """Report where the attempt stands and, once it is approved, issue the session.

    Only the browser that started the attempt knows `attempt_key`. An approval is
    exchanged for a session exactly once.
    """
    with transaction.atomic():
        challenge = LoginChallenge.objects.select_for_update().filter(pk=challenge_id).first()
        if challenge is None or not hmac.compare_digest(
            challenge.attempt_key_hash, hash_token(attempt_key)
        ):
            return LoginProgress(LoginState.INVALID)

        now = timezone.now()
        status = challenge.status
        if status == LoginChallengeStatus.DENIED:
            return LoginProgress(LoginState.DENIED)
        if status in (LoginChallengeStatus.CONSUMED, LoginChallengeStatus.CANCELLED):
            return LoginProgress(LoginState.INVALID)
        if challenge.expires_at <= now:
            return LoginProgress(LoginState.EXPIRED)
        if status == LoginChallengeStatus.PENDING:
            return LoginProgress(LoginState.PENDING, delivery=ChallengeDelivery(challenge.delivery))

        # Approved and still in time.
        user = User.objects.select_for_update().get(pk=challenge.user_id)
        if not user.is_active or user.telegram_user_id != challenge.telegram_user_id:
            challenge.status = LoginChallengeStatus.CANCELLED
            challenge.save(update_fields=["status"])
            return LoginProgress(LoginState.INVALID)

        session_key = secrets.token_urlsafe(32)
        challenge.status = LoginChallengeStatus.CONSUMED
        challenge.consumed_at = now
        challenge.save(update_fields=["status", "consumed_at"])
        try:
            with transaction.atomic():
                session = Session.objects.create(
                    user=user,
                    challenge=challenge,
                    token_hash=hash_token(session_key),
                    permissions_version=user.permissions_version,
                    ip_address=ip_address,
                    user_agent=_clean_user_agent(user_agent),
                    created_at=now,
                    expires_at=now + SESSION_LIFETIME,
                )
        except IntegrityError:
            # A session already exists for this challenge: never issue a second one.
            transaction.set_rollback(True)
            return LoginProgress(LoginState.INVALID)
        user.last_login = now
        user.save(update_fields=["last_login"])
        audit.record(
            actor=Actor.for_user(user),
            action="auth.login_succeeded",
            entity_type="user",
            entity_id=str(user.pk),
            metadata={
                "challenge_id": str(challenge.pk),
                "session_id": str(session.pk),
                "ip_address": ip_address,
                "expires_at": session.expires_at.isoformat(),
            },
        )
    throttling.reset([Subject(ThrottleKind.MFA, str(user.pk))])
    return LoginProgress(LoginState.AUTHENTICATED, session=session, session_key=session_key)
