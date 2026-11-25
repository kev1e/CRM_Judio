"""An employee chooses their own password (D036).

An account is provisioned without a password. Right after the employee binds
Telegram, the bot sends a one-time link to that Telegram account; the page behind
the link sets the password. The link works once, for a limited time, and only
while the account still has no password: changing an existing password is not
possible here (a lost password is a recovery action, Q28/REC-01).

Setting the password does not sign anybody in: the normal login with approval in
Telegram follows.
"""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity import services, throttling
from crm.identity.enrollment import IssuedToken
from crm.identity.models import PasswordSetupToken, ThrottleKind, User
from crm.identity.throttling import Subject

BOT_ACTOR = Actor.system("telegram-bot")
WEB_ACTOR = Actor.system("password-setup")


class SetupLinkRejectedError(DomainError):
    """The link was not accepted. One generic outcome; the reason is audited."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            "setup_link_rejected", "The link is not valid any more. Ask the CRM bot for a new one."
        )
        self.reason = reason


def _hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def setup_url(token: IssuedToken) -> str:
    # The token travels in the fragment: browsers do not send it to the server,
    # so it reaches neither access logs nor the Referer header.
    return f"{settings.WEB_PUBLIC_URL}/set-password#{token.value}"


def issue_for_telegram_account(*, telegram_user_id: int) -> IssuedToken | None:
    """Issue a setup link for the account bound to this Telegram ID, if it still
    needs a password. Called by the bot with the sender's ID from the update.

    Returns None when there is nothing to do (no such binding, deactivated, a
    password already exists) or when links were requested too often; the caller
    answers the same way in all these cases.
    """
    subject = Subject(ThrottleKind.SETUP_LINK_ISSUE, str(telegram_user_id))
    with transaction.atomic():
        user = (
            User.objects.select_for_update()
            .filter(telegram_user_id=telegram_user_id, is_active=True)
            .first()
        )
        if user is None or user.has_usable_password():
            return None
        if throttling.retry_after([subject]):
            return None

        now = timezone.now()
        PasswordSetupToken.objects.filter(
            user=user, used_at__isnull=True, revoked_at__isnull=True
        ).update(revoked_at=now)
        raw_token = secrets.token_urlsafe(32)
        expires_at = now + timedelta(minutes=settings.PASSWORD_SETUP_TOKEN_TTL_MINUTES)
        PasswordSetupToken.objects.create(
            user=user, token_hash=_hash(raw_token), expires_at=expires_at
        )
        audit.record(
            actor=BOT_ACTOR,
            action="password_setup.issued",
            entity_type="user",
            entity_id=str(user.pk),
            metadata={"expires_at": expires_at.isoformat()},
        )
    throttling.register_failure([subject])
    return IssuedToken(value=raw_token, expires_at=expires_at)


def _reject(reason: str, *, ip_address: str | None, user: User | None) -> SetupLinkRejectedError:
    throttling.register_failure([_source(ip_address)])
    audit.record(
        actor=WEB_ACTOR,
        action="password_setup.rejected",
        entity_type="user" if user else "source",
        entity_id=str(user.pk) if user else (ip_address or "unknown"),
        metadata={"reason": reason, "ip_address": ip_address},
    )
    return SetupLinkRejectedError(reason)


def _source(ip_address: str | None) -> Subject:
    return Subject(ThrottleKind.SETUP_LINK_USE, ip_address or "unknown")


def set_initial_password(*, raw_token: str, password: str, ip_address: str | None) -> User:
    """Set the first password of the account the link was issued for.

    A password that does not meet the policy raises `DomainError("invalid_password")`
    and leaves the link usable, so the employee can simply choose another one.
    """
    if throttling.retry_after([_source(ip_address)]):
        raise SetupLinkRejectedError("throttled")

    user: User | None = None
    reason: str | None = None
    with transaction.atomic():
        token = (
            PasswordSetupToken.objects.select_for_update()
            .filter(token_hash=_hash(raw_token))
            .first()
        )
        if token is None:
            reason = "unknown_token"
        else:
            user = User.objects.select_for_update().get(pk=token.user_id)
            now = timezone.now()
            if token.used_at is not None:
                reason = "token_used"
            elif token.revoked_at is not None:
                reason = "token_revoked"
            elif token.expires_at <= now:
                reason = "token_expired"
            elif not user.is_active:
                reason = "user_inactive"
            elif user.telegram_user_id is None:
                reason = "telegram_not_bound"
            elif user.has_usable_password():
                reason = "password_already_set"
            else:
                # Raises DomainError("invalid_password") and rolls back: the link stays valid.
                services.set_password(actor=WEB_ACTOR, user=user, raw_password=password)
                token.used_at = now
                token.save(update_fields=["used_at"])
                return user

    raise _reject(reason or "unknown_token", ip_address=ip_address, user=user)
