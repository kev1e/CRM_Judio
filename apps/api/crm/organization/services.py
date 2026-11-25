"""Departments, memberships and managers (S2; Q01, Q08, D018).

* Belonging to a department and managing it are separate facts.
* An employee may belong to any number of departments; as soon as they belong to
  one, exactly one membership is the primary one. The first membership becomes
  primary; afterwards only an administrator action moves it.
* Managing a department is what gives a manager's permissions their reach
  (`MANAGED_DEPARTMENTS`). The built-in `department_manager` role follows the
  fact: it is held exactly while the user manages at least one department.

Changing who belongs where or who manages what is `department.manage`
(administrator). Every change bumps the permission version of the people it
affects and is audited in the same transaction.
"""

from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from crm.access import services as access
from crm.access.permissions import DEPARTMENT_MANAGER_ROLE_KEY, Scope
from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity.models import User
from crm.organization.models import Department, DepartmentManager, DepartmentMembership

_MANAGE = "department.manage"


def _require_manage(actor: Actor) -> None:
    access.require_permission(actor, _MANAGE, at_least=Scope.COMPANY)


def _clean_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name:
        raise DomainError("invalid_department_name", "The department name must not be empty.")
    if len(name) > 150:
        raise DomainError("invalid_department_name", "The department name is too long.")
    return name


def _active_user(user_id: UUID) -> User:
    user = User.objects.select_for_update().filter(pk=user_id).first()
    if user is None:
        raise DomainError("user_not_found", "No such employee.")
    if not user.is_active:
        raise DomainError("user_inactive", "The account is deactivated.")
    return user


def _open_department(department_id: UUID) -> Department:
    department = Department.objects.select_for_update().filter(pk=department_id).first()
    if department is None:
        raise DomainError("department_not_found", "No such department.")
    if not department.is_active:
        raise DomainError("department_closed", "The department is closed.")
    return department


# --- Reading ----------------------------------------------------------------


def visible_departments(*, actor: Actor) -> QuerySet[Department]:
    """Departments the actor may see: all of them, or the managed ones."""
    scope = access.require_department_scope(actor, "department.read")
    departments = Department.objects.order_by("name")
    if scope.company:
        return departments
    return departments.filter(pk__in=scope.department_ids)


# --- Departments ------------------------------------------------------------


def create_department(*, actor: Actor, name: str) -> Department:
    _require_manage(actor)
    clean = _clean_name(name)
    try:
        with transaction.atomic():
            department = Department.objects.create(name=clean)
            audit.record(
                actor=actor,
                action="department.created",
                entity_type="department",
                entity_id=str(department.pk),
                metadata={"name": clean},
            )
    except IntegrityError as exc:
        raise DomainError(
            "department_name_taken", "A department with this name already exists."
        ) from exc
    return department


def rename_department(*, actor: Actor, department_id: UUID, name: str) -> Department:
    _require_manage(actor)
    clean = _clean_name(name)
    try:
        with transaction.atomic():
            department = Department.objects.select_for_update().filter(pk=department_id).first()
            if department is None:
                raise DomainError("department_not_found", "No such department.")
            if department.name != clean:
                before = department.name
                department.name = clean
                department.save(update_fields=["name"])
                audit.record(
                    actor=actor,
                    action="department.renamed",
                    entity_type="department",
                    entity_id=str(department.pk),
                    metadata={"before": before, "after": clean},
                )
    except IntegrityError as exc:
        raise DomainError(
            "department_name_taken", "A department with this name already exists."
        ) from exc
    return department


def set_department_active(*, actor: Actor, department_id: UUID, active: bool) -> Department:
    """Close or reopen a department.

    A closed department gives its managers no reach. It cannot be closed while it
    is somebody's primary department: an administrator moves those people first,
    nothing is reassigned silently.
    """
    _require_manage(actor)
    with transaction.atomic():
        department = Department.objects.select_for_update().filter(pk=department_id).first()
        if department is None:
            raise DomainError("department_not_found", "No such department.")
        if department.is_active == active:
            return department
        if (
            not active
            and department.memberships.filter(is_primary=True, user__is_active=True).exists()
        ):
            raise DomainError(
                "department_is_primary",
                "The department is the primary one for some employees; move them first.",
            )
        department.is_active = active
        department.save(update_fields=["is_active"])
        access.bump_permissions_version(department.managers.values_list("user_id", flat=True))
        audit.record(
            actor=actor,
            action="department.reopened" if active else "department.closed",
            entity_type="department",
            entity_id=str(department.pk),
        )
    return department


# --- Memberships ------------------------------------------------------------


def add_member(*, actor: Actor, department_id: UUID, user_id: UUID) -> DepartmentMembership:
    """Put an employee into a department. Their first department becomes primary."""
    _require_manage(actor)
    with transaction.atomic():
        department = _open_department(department_id)
        user = _active_user(user_id)
        existing = DepartmentMembership.objects.filter(user=user, department=department).first()
        if existing is not None:
            return existing
        is_first = not DepartmentMembership.objects.filter(user=user).exists()
        membership = DepartmentMembership.objects.create(
            user=user, department=department, is_primary=is_first
        )
        access.bump_permissions_version([user.pk])
        audit.record(
            actor=actor,
            action="department.member_added",
            entity_type="user",
            entity_id=str(user.pk),
            metadata={"department_id": str(department.pk), "is_primary": is_first},
        )
    return membership


def remove_member(*, actor: Actor, department_id: UUID, user_id: UUID) -> bool:
    """Take an employee out of a department. Returns False if they were not in it.

    The primary department cannot be left while other memberships exist: choose
    another primary one first (Q01: never picked automatically).
    """
    _require_manage(actor)
    with transaction.atomic():
        User.objects.select_for_update().filter(pk=user_id).first()
        membership = DepartmentMembership.objects.filter(
            user_id=user_id, department_id=department_id
        ).first()
        if membership is None:
            return False
        if (
            membership.is_primary
            and DepartmentMembership.objects.filter(user_id=user_id)
            .exclude(pk=membership.pk)
            .exists()
        ):
            raise DomainError(
                "primary_department_required",
                "Choose another primary department for the employee first.",
            )
        membership.delete()
        access.bump_permissions_version([user_id])
        audit.record(
            actor=actor,
            action="department.member_removed",
            entity_type="user",
            entity_id=str(user_id),
            metadata={"department_id": str(department_id)},
        )
    return True


def set_primary_department(*, actor: Actor, user_id: UUID, department_id: UUID) -> None:
    """Make one of the employee's departments the primary one (Q01: administrator only)."""
    _require_manage(actor)
    with transaction.atomic():
        user = _active_user(user_id)
        _open_department(department_id)
        target = DepartmentMembership.objects.filter(user=user, department_id=department_id).first()
        if target is None:
            raise DomainError("not_a_member", "The employee does not belong to this department.")
        if target.is_primary:
            return
        previous = DepartmentMembership.objects.filter(user=user, is_primary=True).first()
        if previous is not None:
            previous.is_primary = False
            previous.save(update_fields=["is_primary"])
        target.is_primary = True
        target.save(update_fields=["is_primary"])
        access.bump_permissions_version([user.pk])
        audit.record(
            actor=actor,
            action="department.primary_changed",
            entity_type="user",
            entity_id=str(user.pk),
            metadata={
                "before": str(previous.department_id) if previous else None,
                "after": str(department_id),
            },
        )


def place_new_employee(*, actor: Actor, user: User, department_id: UUID) -> None:
    """Put a freshly created account into its first (primary) department.

    For the provisioning flow only: the caller has already checked that the actor
    may create accounts in this department (D018), so `department.manage` is not
    required here. Runs inside the caller's transaction.
    """
    department = _open_department(department_id)
    DepartmentMembership.objects.create(user=user, department=department, is_primary=True)
    audit.record(
        actor=actor,
        action="department.member_added",
        entity_type="user",
        entity_id=str(user.pk),
        metadata={"department_id": str(department.pk), "is_primary": True},
    )


# --- Managers ---------------------------------------------------------------


def _sync_manager_role(actor: Actor, user: User) -> None:
    manages_any = DepartmentManager.objects.filter(user_id=user.pk).exists()
    access.sync_system_role(
        actor=actor, user=user, role_key=DEPARTMENT_MANAGER_ROLE_KEY, should_hold=manages_any
    )


def add_manager(
    *, actor: Actor, department_id: UUID, user_id: UUID, designated: bool = False
) -> DepartmentManager:
    """Make an employee a manager of a department.

    The first manager of a department becomes its designated one. `designated=True`
    moves the designation to this manager explicitly.
    """
    _require_manage(actor)
    with transaction.atomic():
        department = _open_department(department_id)
        user = _active_user(user_id)
        manager, created = DepartmentManager.objects.get_or_create(department=department, user=user)
        has_designated = (
            DepartmentManager.objects.filter(department=department, is_designated=True)
            .exclude(pk=manager.pk)
            .exists()
        )
        make_designated = (designated or not has_designated) and not manager.is_designated
        if make_designated:
            DepartmentManager.objects.filter(department=department, is_designated=True).update(
                is_designated=False
            )
            manager.is_designated = True
            manager.save(update_fields=["is_designated"])
        if created or make_designated:
            _sync_manager_role(actor, user)
            access.bump_permissions_version([user.pk])
            audit.record(
                actor=actor,
                action="department.manager_added" if created else "department.manager_designated",
                entity_type="user",
                entity_id=str(user.pk),
                metadata={
                    "department_id": str(department.pk),
                    "is_designated": manager.is_designated,
                },
            )
    return manager


def remove_manager(*, actor: Actor, department_id: UUID, user_id: UUID) -> bool:
    """Stop an employee managing a department. Returns False if they did not.

    The designated manager can be removed only when they are the last manager of
    the department or after the designation has been moved to somebody else.
    """
    _require_manage(actor)
    with transaction.atomic():
        Department.objects.select_for_update().filter(pk=department_id).first()
        manager = DepartmentManager.objects.filter(
            department_id=department_id, user_id=user_id
        ).first()
        if manager is None:
            return False
        if (
            manager.is_designated
            and DepartmentManager.objects.filter(department_id=department_id)
            .exclude(pk=manager.pk)
            .exists()
        ):
            raise DomainError(
                "designated_manager_required",
                "Designate another manager of the department first.",
            )
        user = manager.user
        manager.delete()
        _sync_manager_role(actor, user)
        access.bump_permissions_version([user_id])
        audit.record(
            actor=actor,
            action="department.manager_removed",
            entity_type="user",
            entity_id=str(user_id),
            metadata={"department_id": str(department_id)},
        )
    return True
