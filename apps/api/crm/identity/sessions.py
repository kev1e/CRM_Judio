"""Web sessions: issuing is done by `auth.complete_login`; this module checks and
revokes them. It depends only on the models and the audit log, so every other
identity service can call it.
"""

import hashlib
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from crm.audit import services as audit
from crm.common.actors import Actor
from crm.identity.models import LoginChallenge, LoginChallengeStatus, Session, User

# Q13: absolute maximum; a session is never prolonged.
SESSION_LIFETIME = timedelta(hours=12)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def authenticate(raw_token: str) -> Session | None:
    """The live session for a browser token, or None.

    Runs on every authenticated request: expiry, revocation and the account's
    active state are read from the database each time, so they apply at once.
    """
    if not raw_token or len(raw_token) > 128:
        return None
    return (
        Session.objects.select_related("user")
        .filter(
            token_hash=hash_token(raw_token),
            revoked_at__isnull=True,
            expires_at__gt=timezone.now(),
            user__is_active=True,
        )
        .first()
    )


def revoke(*, actor: Actor, session: Session, reason: str) -> bool:
    """Revoke one session. Returns False if it was already revoked."""
    with transaction.atomic():
        changed = Session.objects.filter(pk=session.pk, revoked_at__isnull=True).update(
            revoked_at=timezone.now(), revoked_reason=reason
        )
        if changed:
            audit.record(
                actor=actor,
                action="session.revoked",
                entity_type="user",
                entity_id=str(session.user_id),
                metadata={"session_id": str(session.pk), "reason": reason},
            )
    return bool(changed)


def revoke_all_for_user(*, actor: Actor, user: User, reason: str) -> int:
    """Revoke every live session of the user and cancel login attempts that are
    still waiting. Must run inside the transaction that makes them invalid
    (password change, deactivation, Telegram re-binding)."""
    now = timezone.now()
    sessions = Session.objects.filter(user_id=user.pk, revoked_at__isnull=True).update(
        revoked_at=now, revoked_reason=reason
    )
    challenges = LoginChallenge.objects.filter(
        user_id=user.pk,
        status__in=[LoginChallengeStatus.PENDING, LoginChallengeStatus.APPROVED],
    ).update(status=LoginChallengeStatus.CANCELLED)
    if sessions or challenges:
        audit.record(
            actor=actor,
            action="session.revoked_all",
            entity_type="user",
            entity_id=str(user.pk),
            metadata={"reason": reason, "sessions": sessions, "challenges": challenges},
        )
    return sessions
