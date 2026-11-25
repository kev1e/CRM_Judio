"""First-time binding of a Telegram account to a CRM account (Q11).

Flow: an authorized person issues a one-time token for an account; the employee
sends it to the bot in a private chat; the bot calls `redeem_token` with the
numeric Telegram ID of the sender; the ID is bound atomically.

The Telegram username is stored only as a display label. Re-binding an account
that is already bound is a recovery action (Q12, REC-01) and is not possible here.
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from crm.access import services as access
from crm.access.permissions import Scope
from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity import throttling
from crm.identity.models import TelegramEnrollmentToken, ThrottleKind, User
from crm.identity.throttling import Subject

logger = logging.getLogger(__name__)

BOT_ACTOR = Actor.system("telegram-bot")
_TELEGRAM_USERNAME_MAX = 64


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """Returned once to the issuer. `value` is never stored or logged."""

    value: str
    expires_at: datetime

    def __repr__(self) -> str:  # keep the secret out of logs and tracebacks
        return f"IssuedToken(expires_at={self.expires_at.isoformat()})"


class EnrollmentRejectedError(DomainError):
    """The token was not accepted. Callers get one generic outcome; the exact
    reason is written to the audit log only, so a probing sender learns nothing."""

    def __init__(self, reason: str) -> None:
        super().__init__("enrollment_rejected", "The binding code is not valid.")
        self.reason = reason


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _issue(*, actor: Actor, user: User, action: str) -> IssuedToken:
    """Create a pending token for a locked, validated user. Runs in the caller's transaction."""
    locked = User.objects.select_for_update().get(pk=user.pk)
    if not locked.is_active:
        raise DomainError("user_inactive", "A deactivated account cannot be bound to Telegram.")
    if locked.telegram_user_id is not None:
        raise DomainError(
            "telegram_already_bound",
            "The account is already bound to Telegram; re-binding is a recovery action.",
        )

    now = timezone.now()
    revoked = TelegramEnrollmentToken.objects.filter(
        user=locked, used_at__isnull=True, revoked_at__isnull=True
    ).update(revoked_at=now)

    raw_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(minutes=settings.TELEGRAM_ENROLLMENT_TOKEN_TTL_MINUTES)
    TelegramEnrollmentToken.objects.create(
        user=locked, token_hash=_hash(raw_token), expires_at=expires_at
    )
    audit.record(
        actor=actor,
        action=action,
        entity_type="user",
        entity_id=str(locked.pk),
        metadata={"expires_at": expires_at.isoformat(), "replaced_pending": revoked},
    )
    return IssuedToken(value=raw_token, expires_at=expires_at)


def issue_token(*, actor: Actor, user: User) -> IssuedToken:
    """Issue a binding token for an account that is not bound yet.

    Allowed to whoever may provision accounts (Q11). Until departments exist (S2)
    that means the company-wide `user.create` grant.
    """
    access.require_permission(actor, "user.create", at_least=Scope.COMPANY)
    with transaction.atomic():
        return _issue(actor=actor, user=user, action="telegram.enrollment_issued")


def issue_first_administrator_token(*, operator: str, crm_login: str) -> IssuedToken:
    """Issue a binding token for an administrator from the command line.

    Works only while the installation is still being set up, i.e. no active
    administrator has a bound Telegram account. After that point tokens are issued
    by signed-in administrators; this is not the emergency procedure of REC-02.
    """
    actor = Actor.cli(operator)
    with transaction.atomic():
        access.claim_setup_phase()
        user = User.objects.filter(crm_login=crm_login.strip().lower()).first()
        if user is None or not access.is_administrator(user):
            raise DomainError("not_an_administrator", "No active administrator has this login.")
        return _issue(actor=actor, user=user, action="telegram.enrollment_issued")


def _enrollment_subject(telegram_user_id: int) -> Subject:
    return Subject(ThrottleKind.ENROLLMENT, str(telegram_user_id))


def _reject(
    reason: str, *, telegram_user_id: int, user: User | None = None
) -> EnrollmentRejectedError:
    """Record a refused attempt. Runs outside the failed transaction so it is kept."""
    if reason != "throttled":
        throttling.register_failure([_enrollment_subject(telegram_user_id)])
    audit.record(
        actor=BOT_ACTOR,
        action="telegram.enrollment_rejected",
        entity_type="user" if user else "telegram_account",
        entity_id=str(user.pk) if user else str(telegram_user_id),
        metadata={"reason": reason, "telegram_user_id": telegram_user_id},
    )
    return EnrollmentRejectedError(reason)


def _clean_username(raw: str | None) -> str:
    return (raw or "").strip().lstrip("@")[:_TELEGRAM_USERNAME_MAX]


def redeem_token(
    *,
    raw_token: str,
    telegram_user_id: int,
    telegram_username: str | None,
    chat_is_private: bool,
) -> User:
    """Bind the sender's Telegram ID to the account the token was issued for.

    `telegram_user_id` must come from Telegram's own update data (the sender of the
    private message), never from text typed by the user.
    """
    if (
        not isinstance(telegram_user_id, int)
        or isinstance(telegram_user_id, bool)
        or telegram_user_id <= 0
    ):
        raise ValueError("telegram_user_id must be a positive integer taken from the update.")
    if not chat_is_private:
        # A token typed into a group is visible to others: burn nothing, accept nothing.
        raise _reject("not_private_chat", telegram_user_id=telegram_user_id)
    # Q13: repeated wrong codes from one Telegram account wait progressively longer.
    if throttling.retry_after([_enrollment_subject(telegram_user_id)]):
        raise _reject("throttled", telegram_user_id=telegram_user_id)

    target: User | None = None
    reason: str | None = None
    try:
        with transaction.atomic():
            token = (
                TelegramEnrollmentToken.objects.select_for_update()
                .filter(token_hash=_hash(raw_token))
                .first()
            )
            if token is None:
                reason = "unknown_token"
            else:
                target = User.objects.select_for_update().get(pk=token.user_id)
                now = timezone.now()
                if token.used_at is not None:
                    reason = "token_used"
                elif token.revoked_at is not None:
                    reason = "token_revoked"
                elif token.expires_at <= now:
                    reason = "token_expired"
                elif not target.is_active:
                    reason = "user_inactive"
                elif target.telegram_user_id is not None:
                    reason = "user_already_bound"
                elif User.objects.filter(telegram_user_id=telegram_user_id).exists():
                    reason = "telegram_account_in_use"

            if reason is None and token is not None and target is not None:
                target.telegram_user_id = telegram_user_id
                target.telegram_username = _clean_username(telegram_username)
                target.telegram_bound_at = now
                target.save(
                    update_fields=[
                        "telegram_user_id", "telegram_username", "telegram_bound_at", "updated_at",
                    ]
                )  # fmt: skip
                token.used_at = now
                token.save(update_fields=["used_at"])
                audit.record(
                    actor=BOT_ACTOR,
                    action="telegram.bound",
                    entity_type="user",
                    entity_id=str(target.pk),
                    metadata={"telegram_user_id": telegram_user_id},
                )
                return target
    except IntegrityError:
        # Two requests bound the same Telegram account at the same instant.
        reason = "telegram_account_in_use"

    raise _reject(reason or "unknown_token", telegram_user_id=telegram_user_id, user=target)
