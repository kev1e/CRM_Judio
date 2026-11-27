"""Managing employee accounts (S1.4): the use cases behind the Users screen.

Every function authorizes its actor through `crm.access`. Until departments exist
(S2) only company-wide grants count, i.e. in practice the administrator; managers
get their department-scoped part with S2.
"""

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from crm.access import services as access
from crm.access.models import Role, UserRole
from crm.access.permissions import ADMINISTRATOR_ROLE_KEY, Scope
from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.identity import enrollment, services, sessions
from crm.identity.models import PasswordSetupToken, TelegramEnrollmentToken, User
from crm.organization import services as organization

RESPONSIBILITY_MAX_LENGTH = 300


@dataclass(frozen=True, slots=True)
class ProvisionedUser:
    user: User
    binding_token: enrollment.IssuedToken


def list_users(*, actor: Actor) -> QuerySet[User]:
    """Accounts the actor may see: all of them, or the members of managed departments."""
    scope = access.require_department_scope(actor, "user.read")
    accounts = User.objects.order_by("display_name", "crm_login")
    if scope.company:
        return accounts
    return accounts.filter(
        department_memberships__department_id__in=scope.department_ids
    ).distinct()


def provision_user(
    *,
    actor: Actor,
    crm_login: str,
    display_name: str,
    email: str | None = None,
    department_id: UUID | None = None,
) -> ProvisionedUser:
    """Create an account without a password and a one-time Telegram binding code.

    The employee binds Telegram with the code and then chooses a password through
    the link the bot sends (D036). The new account holds no role.

    `department_id` becomes the employee's primary department. An administrator
    may leave it out and place the employee later; a manager must name one of the
    departments they manage (D018).
    """
    scope = access.require_department_scope(actor, "user.create")
    if not scope.company and not scope.covers(department_id):
        raise PermissionDeniedError()
    with transaction.atomic():
        user = services.create_user(
            actor=actor, crm_login=crm_login, display_name=display_name, email=email
        )
        if department_id is not None:
            organization.place_new_employee(actor=actor, user=user, department_id=department_id)
        token = enrollment.issue_token(actor=actor, user=user)
    return ProvisionedUser(user=user, binding_token=token)


def reissue_binding_token(*, actor: Actor, user: User) -> enrollment.IssuedToken:
    """A fresh binding code for an account that is not bound yet; the old one stops working."""
    return enrollment.issue_token(actor=actor, user=user)


def deactivate_user(*, actor: Actor, user: User) -> bool:
    """Close the account: no login, no open session, no pending code or link.

    Returns False if it was already deactivated. The employee's open tasks are
    handed over in the same transaction (D019, Q08); without somebody to take
    them the deactivation is refused.
    """
    access.require_permission(actor, "user.deactivate", at_least=Scope.COMPANY)
    if actor.user is not None and actor.user.pk == user.pk:
        raise DomainError("cannot_deactivate_self", "You cannot deactivate your own account.")
    with transaction.atomic():
        # Locking the administrator role serialises this with role revocation, so
        # two requests cannot remove the last two administrators at once.
        admin_role = Role.objects.select_for_update().get(
            key=ADMINISTRATOR_ROLE_KEY, is_system=True
        )
        access.require_permission(actor, "user.deactivate", at_least=Scope.COMPANY)
        target = User.objects.select_for_update().get(pk=user.pk)
        if not target.is_active:
            return False
        is_admin = UserRole.objects.filter(user=target, role=admin_role).exists()
        if is_admin and not (
            UserRole.objects.filter(role=admin_role, user__is_active=True)
            .exclude(user=target)
            .exists()
        ):
            raise DomainError(
                "last_administrator", "The last active administrator cannot be deactivated."
            )

        # D019/Q08: open tasks go to the designated manager of the primary
        # department, or the deactivation is refused. Same transaction.
        from crm.tasks import services as tasks

        handed_over = tasks.hand_over_open_tasks(actor=actor, user=target)

        now = timezone.now()
        target.is_active = False
        target.deactivated_at = now
        target.save(update_fields=["is_active", "deactivated_at", "updated_at"])
        access.bump_permissions_version([target.pk])
        sessions.revoke_all_for_user(actor=actor, user=target, reason="deactivated")
        pending = {"used_at__isnull": True, "revoked_at__isnull": True}
        TelegramEnrollmentToken.objects.filter(user=target, **pending).update(revoked_at=now)
        PasswordSetupToken.objects.filter(user=target, **pending).update(revoked_at=now)
        audit.record(
            actor=actor,
            action="user.deactivated",
            entity_type="user",
            entity_id=str(target.pk),
            metadata={"tasks_handed_over": handed_over},
        )
    user.is_active, user.deactivated_at = False, now
    return True


def reactivate_user(*, actor: Actor, user: User) -> bool:
    """Open a deactivated account again. Its roles, password and Telegram binding
    are as they were; nothing that was revoked comes back. Returns False if the
    account was active already."""
    access.require_permission(actor, "user.deactivate", at_least=Scope.COMPANY)
    with transaction.atomic():
        target = User.objects.select_for_update().get(pk=user.pk)
        if target.is_active:
            return False
        target.is_active = True
        target.deactivated_at = None
        target.save(update_fields=["is_active", "deactivated_at", "updated_at"])
        access.bump_permissions_version([target.pk])
        audit.record(
            actor=actor,
            action="user.reactivated",
            entity_type="user",
            entity_id=str(target.pk),
        )
    user.is_active, user.deactivated_at = True, None
    return True


def set_responsibility(*, actor: Actor, user: User, text: str) -> User:
    """Write down what the employee answers for (shown in the company structure).

    A description only: it changes nobody's rights. Editing account details is
    `user.update` (administrator).
    """
    access.require_permission(actor, "user.update", at_least=Scope.COMPANY)
    clean = " ".join(text.split())
    if len(clean) > RESPONSIBILITY_MAX_LENGTH:
        raise DomainError("invalid_responsibility", "The description is too long.")
    with transaction.atomic():
        target = User.objects.select_for_update().get(pk=user.pk)
        if target.responsibility != clean:
            before = target.responsibility
            target.responsibility = clean
            target.save(update_fields=["responsibility", "updated_at"])
            audit.record(
                actor=actor,
                action="user.responsibility_changed",
                entity_type="user",
                entity_id=str(target.pk),
                metadata={"before": before, "after": clean},
            )
    user.responsibility = clean
    return user


def active_by_telegram_id(telegram_user_id: int) -> User | None:
    """The active account bound to this numeric Telegram ID (Q30) — how the bot
    learns who is talking to it. Read from the database on every call (D020)."""
    return User.objects.filter(telegram_user_id=telegram_user_id, is_active=True).first()
