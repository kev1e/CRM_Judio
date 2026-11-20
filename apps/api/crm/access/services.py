"""The single authorization service (D032-C1).

REST views, Celery tasks and Telegram handlers ask this module whether an actor
may do something; nothing else decides. Grants are read from PostgreSQL on every
check, so a change of rights applies to already open sessions immediately (D020).

Resolution of the MANAGED_DEPARTMENTS scope against concrete departments is added
with the organization module (S2). Until then a caller can only ask for a minimum
scope, and department-scoped grants do not satisfy a COMPANY-level check.
"""

import re
from collections.abc import Mapping

from django.db import IntegrityError, transaction

from crm.access.models import ROLE_KEY_REGEX, Role, RoleGrant, UserRole
from crm.access.permissions import ADMINISTRATOR_ROLE_KEY, REGISTRY, Scope
from crm.audit import services as audit
from crm.common.actors import Actor, ActorType
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.identity import services as identity
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
    grants: dict[str, Scope] = {}
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
        identity.bump_permissions_version(holders)
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
    identity.bump_permissions_version([user.pk])
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
        identity.bump_permissions_version([user.pk])
        audit.record(
            actor=actor,
            action="role.revoked",
            entity_type="user",
            entity_id=str(user.pk),
            metadata={"role": locked_role.key},
        )
        return True


# --- First administrator ----------------------------------------------------


def create_first_administrator(
    *, operator: str, crm_login: str, display_name: str, password: str
) -> User:
    """Create the very first administrator on an installation that has none.

    This is not the emergency (break-glass) procedure of REC-02: it refuses to run
    as soon as any active administrator exists.
    """
    actor = Actor.cli(operator)
    with transaction.atomic():
        role = Role.objects.select_for_update().get(key=ADMINISTRATOR_ROLE_KEY, is_system=True)
        if UserRole.objects.filter(role=role, user__is_active=True).exists():
            raise DomainError(
                "administrator_exists",
                "An active administrator already exists; this command only sets up the first one.",
            )
        user = identity.create_user(
            actor=actor, crm_login=crm_login, display_name=display_name, password=password
        )
        _link_role(actor=actor, user=user, role=role)
    user.refresh_from_db()
    return user
