"""Catalogue of CRM permissions (D032-C1).

A permission is a stable code plus the scopes in which it may be granted. Roles
stored in PostgreSQL refer to these codes; a code that is not listed here cannot
be granted. New permissions are added together with the feature that checks them.
"""

from dataclasses import dataclass
from enum import StrEnum


class Scope(StrEnum):
    """How far a grant reaches. Ordered from narrowest to widest."""

    OWN = "own"
    MANAGED_DEPARTMENTS = "managed_departments"
    COMPANY = "company"

    @property
    def breadth(self) -> int:
        return _BREADTH[self]

    def covers(self, other: Scope) -> bool:
        return self.breadth >= other.breadth


_BREADTH = {Scope.OWN: 1, Scope.MANAGED_DEPARTMENTS: 2, Scope.COMPANY: 3}


@dataclass(frozen=True, slots=True)
class PermissionDef:
    code: str
    description: str
    scopes: frozenset[Scope]
    # Grantable only through a built-in system role, never through a custom role.
    system_role_only: bool = False


_COMPANY_ONLY = frozenset({Scope.COMPANY})
_DEPARTMENT_OR_COMPANY = frozenset({Scope.MANAGED_DEPARTMENTS, Scope.COMPANY})

_ANY_SCOPE = frozenset({Scope.OWN, Scope.MANAGED_DEPARTMENTS, Scope.COMPANY})

# Task permissions. For a task the scopes mean: OWN — tasks assigned to the user;
# MANAGED_DEPARTMENTS — additionally, tasks whose responsible department the user
# manages; COMPANY — every task. A wider scope includes the narrower ones.
_TASK = (
    PermissionDef("task.read", "See tasks.", _ANY_SCOPE),
    PermissionDef("task.create", "Create tasks and requests.", _ANY_SCOPE),
    PermissionDef("task.update", "Edit a task's title and description.", _ANY_SCOPE),
    PermissionDef("task.status", "Move a task between statuses, including completion.", _ANY_SCOPE),
    PermissionDef("task.deadline", "Change a task's deadline.", _ANY_SCOPE),
    PermissionDef("task.checkpoints.use", "Add checkpoints and tick them.", _ANY_SCOPE),
    PermissionDef(
        "task.checkpoints.manage", "Rename and remove checkpoints.", _DEPARTMENT_OR_COMPANY
    ),
    PermissionDef("task.priority", "Change a task's priority.", _DEPARTMENT_OR_COMPANY),
    PermissionDef("task.reassign", "Change a task's assignee.", _DEPARTMENT_OR_COMPANY),
    PermissionDef(
        "task.archive", "Archive unfinished tasks and reopen archived ones.", _DEPARTMENT_OR_COMPANY
    ),
    PermissionDef(
        "task.delete", "Move tasks to the trash and restore them.", _DEPARTMENT_OR_COMPANY
    ),
)

_ALL = (
    PermissionDef(
        "user.create",
        "Create employee accounts (D018: administrators; managers within managed departments).",
        _DEPARTMENT_OR_COMPANY,
    ),
    PermissionDef(
        "user.read",
        "See the list of employee accounts and their state.",
        _DEPARTMENT_OR_COMPANY,
    ),
    PermissionDef("user.update", "Edit employee account details.", _COMPANY_ONLY),
    PermissionDef("user.deactivate", "Deactivate and reactivate accounts.", _COMPANY_ONLY),
    PermissionDef(
        "user.email.verify",
        "Confirm an employee's recovery email (Q28: administrator only).",
        _COMPANY_ONLY,
        system_role_only=True,
    ),
    PermissionDef(
        "user.recovery.manage",
        "Run account recovery and Telegram re-binding (Q12, Q28, REC-01: administrator only).",
        _COMPANY_ONLY,
        system_role_only=True,
    ),
    PermissionDef(
        "department.read",
        "See departments, their members and managers.",
        _DEPARTMENT_OR_COMPANY,
    ),
    PermissionDef(
        "department.manage",
        "Create and close departments, change members, managers and primary departments.",
        _COMPANY_ONLY,
        system_role_only=True,
    ),
    PermissionDef(
        "role.manage",
        "Create roles and change their grants.",
        _COMPANY_ONLY,
        system_role_only=True,
    ),
    PermissionDef(
        "role.assign",
        "Give roles to users and take them away.",
        _COMPANY_ONLY,
        system_role_only=True,
    ),
    PermissionDef(
        "audit.read",
        "Read audit events (Q14: administrator company-wide; managers for managed departments; "
        "a superuser only with this separate grant).",
        _DEPARTMENT_OR_COMPANY,
    ),
    PermissionDef(
        "workflow.manage",
        "Configure task statuses and the allowed moves between them (D005, Q09).",
        _COMPANY_ONLY,
        system_role_only=True,
    ),
    *_TASK,
)

REGISTRY: dict[str, PermissionDef] = {p.code: p for p in _ALL}

ADMINISTRATOR_ROLE_KEY = "administrator"
DEPARTMENT_MANAGER_ROLE_KEY = "department_manager"

# What managing a department allows, inside the managed departments only. The role
# is built in and is held exactly by the users who manage at least one department.
DEPARTMENT_MANAGER_GRANTS: dict[str, Scope] = dict.fromkeys(
    (
        "audit.read",
        "department.read",
        "user.create",
        "user.read",
        *(p.code for p in _TASK),
    ),
    Scope.MANAGED_DEPARTMENTS,
)

# Configuration rights only. Deliberately no task permission: being an administrator
# does not make task contents visible (D003).
ADMINISTRATOR_GRANTS: dict[str, Scope] = {
    p.code: Scope.COMPANY for p in _ALL if not p.code.startswith("task.")
}

# What every active employee may do without any role (D002, Q19): work with the
# tasks assigned to them and create tasks for others.
BASELINE_GRANTS: dict[str, Scope] = dict.fromkeys(
    (
        "task.read",
        "task.create",
        "task.update",
        "task.status",
        "task.deadline",
        "task.checkpoints.use",
    ),
    Scope.OWN,
)

SUPERUSER_ROLE_KEY = "superuser"
# Q29: company-wide READ of tasks and nothing else. Every action on a task needs
# its own explicit grant through another role.
SUPERUSER_GRANTS: dict[str, Scope] = {"task.read": Scope.COMPANY}
