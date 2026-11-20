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

_ALL = (
    PermissionDef(
        "user.create",
        "Create employee accounts (D018: administrators; managers within managed departments).",
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
)

REGISTRY: dict[str, PermissionDef] = {p.code: p for p in _ALL}

ADMINISTRATOR_ROLE_KEY = "administrator"

# Configuration rights only. Deliberately no task permission: being an administrator
# does not make task contents visible (D003).
ADMINISTRATOR_GRANTS: dict[str, Scope] = {p.code: Scope.COMPANY for p in _ALL}
