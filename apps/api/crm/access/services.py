"""The single authorization service (D032-C1).

REST views, Celery tasks and Telegram handlers ask this module whether an actor
may do something; nothing else decides. Grants are read from PostgreSQL on every
check, so a change of rights applies to already open sessions immediately (D020).

Resolution of the MANAGED_DEPARTMENTS scope against concrete departments is added
with the organization module (S2). Until then a caller can only ask for a minimum
scope, and department-scoped grants do not satisfy a COMPANY-level check.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F

from crm.access.models import ROLE_KEY_REGEX, Role, RoleGrant, UserRole
from crm.access.permissions import ADMINISTRATOR_ROLE_KEY, BASELINE_GRANTS, REGISTRY, Scope
from crm.audit import services as audit
from crm.common.actors import Actor, ActorType
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.identity.models import User

_ROLE_KEY_RE = re.compile(ROLE_KEY_REGEX)

# --- Reading ----------------------------------------------------------------


def _known(code: str) -> None:
    if code not in REGISTRY:
        # A typo in a permission code must fail loudly, not silently deny or allow.
        raise LookupError(f"Unknown permission code: {code!r}")


def effective_grants(user: User) -> dict[str, Scope]:
    """Widest scope per permission across all roles of an active user."""
    if not User.objects.filter(pk=user.pk, is_active=True).exists():
        return {}
    grants: dict[str, Scope] = dict(BASELINE_GRANTS)
    rows = RoleGrant.objects.filter(role__user_links__user_id=user.pk).values_list(
        "permission_code", "scope"
    )
    for code, raw_scope in rows:
        scope = Scope(raw_scope)
        current = grants.get(code)
        if current is None or scope.breadth > current.breadth:
            grants[code] = scope
    return grants


def scope_for(actor: Actor, code: str) -> Scope | None:
    """The scope in which the actor holds the permission, or None. Deny by default."""
    _known(code)
    if actor.type is not ActorType.USER or actor.user is None:
        return None
    return effective_grants(actor.user).get(code)


def has_permission(actor: Actor, code: str, *, at_least: Scope) -> bool:
    scope = scope_for(actor, code)
    return scope is not None and scope.covers(at_least)


def require_permission(actor: Actor, code: str, *, at_least: Scope) -> Scope:
    scope = scope_for(actor, code)
    if scope is None or not scope.covers(at_least):
        raise PermissionDeniedError()
    return scope


@dataclass(frozen=True, slots=True)
class DepartmentScope:
    """Where a permission applies: everywhere, or in a set of departments."""

    company: bool
    department_ids: frozenset[UUID] = frozenset()

    def __bool__(self) -> bool:
        return self.company or bool(self.department_ids)

    def covers(self, department_id: UUID | None) -> bool:
        return self.company or (department_id is not None and department_id in self.department_ids)

    def covers_any(self, department_ids: Iterable[UUID]) -> bool:
        return self.company or not self.department_ids.isdisjoint(department_ids)


NO_SCOPE = DepartmentScope(company=False)


def managed_department_ids(user: User) -> frozenset[UUID]:
    """Active departments the user manages right now. Read on every check (D020)."""
    from crm.organization.models import DepartmentManager

    return frozenset(
        DepartmentManager.objects.filter(
            user_id=user.pk, user__is_active=True, department__is_active=True
        ).values_list("department_id", flat=True)
    )


def department_scope(actor: Actor, code: str) -> DepartmentScope:
    """Resolve the actor's grant of `code` to concrete departments. Deny by default."""
    scope = scope_for(actor, code)
    if scope is None or actor.user is None:
        return NO_SCOPE
    if scope is Scope.COMPANY:
        return DepartmentScope(company=True)
    if scope is Scope.MANAGED_DEPARTMENTS:
        return DepartmentScope(company=False, department_ids=managed_department_ids(actor.user))
    return NO_SCOPE


def require_department_scope(actor: Actor, code: str) -> DepartmentScope:
    """The actor's scope for `code`; refused when it covers nothing at all."""
    scope = department_scope(actor, code)
    if not scope:
        raise PermissionDeniedError()
    return scope


def require_in_department(actor: Actor, code: str, department_id: UUID | None) -> None:
    if not department_scope(actor, code).covers(department_id):
        raise PermissionDeniedError()


def bump_permissions_version(user_ids: Iterable[UUID]) -> int:
    """Mark everything issued for the users' previous permissions as stale (D020).

    Must run inside the transaction that changes the roles or grants.
    """
    return User.objects.filter(pk__in=list(user_ids)).update(
        permissions_version=F("permissions_version") + 1
    )


def sync_system_role(*, actor: Actor, user: User, role_key: str, should_hold: bool) -> None:
    """Give or take a built-in role that follows from another fact (for example
    "manages at least one department"). Called by the service that owns the fact,
    inside its transaction; that service has already authorized the actor."""
    role = Role.objects.get(key=role_key, is_system=True)
    if should_hold:
        _link_role(actor=actor, user=user, role=role)
        return
    deleted, _ = UserRole.objects.filter(user_id=user.pk, role=role).delete()
    if deleted:
        bump_permissions_version([user.pk])
        audit.record(
            actor=actor,
            action="role.revoked",
            entity_type="user",
            entity_id=str(user.pk),
            metadata={"role": role.key},
        )


def is_administrator(user: User) -> bool:
    return UserRole.objects.filter(
        user_id=user.pk,
        user__is_active=True,
        role__key=ADMINISTRATOR_ROLE_KEY,
        role__is_system=True,
    ).exists()


# --- Role administration ----------------------------------------------------


def _validated_grants(grants: Mapping[str, Scope], *, for_system_role: bool) -> dict[str, Scope]:
    validated: dict[str, Scope] = {}
    for code, scope in grants.items():
        definition = REGISTRY.get(code)
        if definition is None:
            raise DomainError("unknown_permission", f"Unknown permission: {code}.")
        try:
            scope = Scope(scope)
        except ValueError as exc:
            raise DomainError("invalid_scope", f"Unknown scope for {code}.") from exc
        if scope not in definition.scopes:
            raise DomainError(
                "invalid_scope", f"Permission {code} cannot be granted in scope {scope.value}."
            )
        if definition.system_role_only and not for_system_role:
            raise DomainError(
                "permission_not_grantable",
                f"Permission {code} belongs to built-in roles only.",
            )
        validated[code] = scope
    return validated


def _grants_of(role: Role) -> dict[str, str]:
    return dict(role.grants.order_by("permission_code").values_list("permission_code", "scope"))


def create_role(*, actor: Actor, key: str, name: str, description: str = "") -> Role:
    require_permission(actor, "role.manage", at_least=Scope.COMPANY)
    key = key.strip().lower()
    if not _ROLE_KEY_RE.fullmatch(key):
        raise DomainError(
            "invalid_role_key",
            "The role key must be 2-63 characters: lowercase Latin letters, digits and '_', "
            "starting with a letter.",
        )
    if not name.strip():
        raise DomainError("invalid_role_name", "The role name must not be empty.")
    try:
        with transaction.atomic():
            role = Role.objects.create(key=key, name=name.strip(), description=description.strip())
            audit.record(
                actor=actor,
                action="role.created",
                entity_type="role",
                entity_id=str(role.pk),
                metadata={"key": key},
            )
    except IntegrityError as exc:
        raise DomainError("role_key_taken", "A role with this key already exists.") from exc
    return role


def set_role_grants(*, actor: Actor, role: Role, grants: Mapping[str, Scope]) -> None:
    """Replace the grants of a custom role. Holders are affected at once."""
    require_permission(actor, "role.manage", at_least=Scope.COMPANY)
    validated = _validated_grants(grants, for_system_role=False)
    with transaction.atomic():
        locked = Role.objects.select_for_update().get(pk=role.pk)
        if locked.is_system:
            raise DomainError("system_role_immutable", "Built-in roles cannot be changed.")
        before = _grants_of(locked)
        after = {code: scope.value for code, scope in sorted(validated.items())}
        if before == after:
            return
        locked.grants.all().delete()
        RoleGrant.objects.bulk_create(
            RoleGrant(role=locked, permission_code=code, scope=scope)
            for code, scope in after.items()
        )
        holders = list(locked.user_links.values_list("user_id", flat=True))
        bump_permissions_version(holders)
        audit.record(
            actor=actor,
            action="role.grants_changed",
            entity_type="role",
            entity_id=str(locked.pk),
            metadata={"key": locked.key, "before": before, "after": after, "holders": len(holders)},
        )


def delete_role(*, actor: Actor, role: Role) -> None:
    require_permission(actor, "role.manage", at_least=Scope.COMPANY)
    with transaction.atomic():
        locked = Role.objects.select_for_update().get(pk=role.pk)
        if locked.is_system:
            raise DomainError("system_role_immutable", "Built-in roles cannot be removed.")
        if locked.user_links.exists():
            raise DomainError("role_in_use", "Take the role away from every user first.")
        audit.record(
            actor=actor,
            action="role.deleted",
            entity_type="role",
            entity_id=str(locked.pk),
            metadata={"key": locked.key, "grants": _grants_of(locked)},
        )
        locked.delete()


def _link_role(*, actor: Actor, user: User, role: Role) -> bool:
    """Attach the role and record it. Returns False when the user already had it."""
    _, created = UserRole.objects.get_or_create(
        user=user, role=role, defaults={"granted_by": actor.user}
    )
    if not created:
        return False
    bump_permissions_version([user.pk])
    audit.record(
        actor=actor,
        action="role.assigned",
        entity_type="user",
        entity_id=str(user.pk),
        metadata={"role": role.key},
    )
    return True


def assign_role(*, actor: Actor, user: User, role: Role) -> bool:
    """Give a role to an active user. Returns False if the user already holds it."""
    require_permission(actor, "role.assign", at_least=Scope.COMPANY)
    with transaction.atomic():
        target = User.objects.select_for_update().get(pk=user.pk)
        if not target.is_active:
            raise DomainError("user_inactive", "A deactivated user cannot receive roles.")
        return _link_role(actor=actor, user=target, role=role)


def revoke_role(*, actor: Actor, user: User, role: Role) -> bool:
    """Take a role away. Returns False if the user did not hold it."""
    require_permission(actor, "role.assign", at_least=Scope.COMPANY)
    with transaction.atomic():
        # Locking the role row serialises concurrent revocations of the same role,
        # so two requests cannot each remove "the other" last administrator.
        locked_role = Role.objects.select_for_update().get(pk=role.pk)
        # Checked again under the lock: the actor's own role may have been taken
        # away by the request that held it a moment ago.
        require_permission(actor, "role.assign", at_least=Scope.COMPANY)
        link = UserRole.objects.filter(user_id=user.pk, role=locked_role).first()
        if link is None:
            return False
        if locked_role.key == ADMINISTRATOR_ROLE_KEY and not (
            UserRole.objects.filter(role=locked_role, user__is_active=True)
            .exclude(user_id=user.pk)
            .exists()
        ):
            raise DomainError(
                "last_administrator", "The last active administrator cannot lose the role."
            )
        link.delete()
        bump_permissions_version([user.pk])
        audit.record(
            actor=actor,
            action="role.revoked",
            entity_type="user",
            entity_id=str(user.pk),
            metadata={"role": locked_role.key},
        )
        return True


# --- First administrator ----------------------------------------------------


def claim_first_administrator_slot() -> Role:
    """Lock the administrator role and make sure nobody holds it yet.

    The only way to obtain the role without an existing administrator starts here.
    It refuses as soon as any active administrator exists; this is not the emergency
    (break-glass) procedure of REC-02. Must run inside the caller's transaction.
    """
    role = Role.objects.select_for_update().get(key=ADMINISTRATOR_ROLE_KEY, is_system=True)
    if UserRole.objects.filter(role=role, user__is_active=True).exists():
        raise DomainError(
            "administrator_exists",
            "An active administrator already exists; this command only sets up the first one.",
        )
    return role


def grant_first_administrator(*, actor: Actor, user: User) -> None:
    """Give the administrator role to the first administrator of the installation."""
    role = claim_first_administrator_slot()
    _link_role(actor=actor, user=user, role=role)


def claim_setup_phase() -> None:
    """Lock the administrator role and make sure the installation is still being set up:
    no active administrator has bound a Telegram account, so nobody can sign in yet.
    Must run inside the caller's transaction.
    """
    role = Role.objects.select_for_update().get(key=ADMINISTRATOR_ROLE_KEY, is_system=True)
    if UserRole.objects.filter(
        role=role, user__is_active=True, user__telegram_user_id__isnull=False
    ).exists():
        raise DomainError(
            "setup_finished",
            "An administrator can already sign in; ask them to issue the binding code.",
        )
