"""Access-separation tests for the authorization service (D032-C1, req. 7, 8, 10)."""

import pytest
from django.utils import timezone

from crm.access import services
from crm.access.models import Role, RoleGrant
from crm.access.permissions import ADMINISTRATOR_GRANTS, REGISTRY, Scope
from crm.common.actors import Actor
from crm.common.exceptions import PermissionDeniedError
from crm.conftest import UserFactory
from crm.identity.models import User

pytestmark = pytest.mark.django_db


def _role(key: str, **grants: Scope) -> Role:
    role = Role.objects.create(key=key, name=key)
    RoleGrant.objects.bulk_create(
        RoleGrant(role=role, permission_code=code.replace("__", "."), scope=scope.value)
        for code, scope in grants.items()
    )
    return role


def _give(user: User, role: Role, admin_actor: Actor) -> None:
    services.assign_role(actor=admin_actor, user=user, role=role)


def test_scopes_are_ordered_from_own_to_company() -> None:
    assert Scope.COMPANY.covers(Scope.MANAGED_DEPARTMENTS)
    assert Scope.MANAGED_DEPARTMENTS.covers(Scope.OWN)
    assert Scope.COMPANY.covers(Scope.COMPANY)
    assert not Scope.OWN.covers(Scope.MANAGED_DEPARTMENTS)
    assert not Scope.MANAGED_DEPARTMENTS.covers(Scope.COMPANY)


def test_user_without_roles_has_no_permissions(make_user: UserFactory) -> None:
    actor = Actor.for_user(make_user())

    assert services.effective_grants(actor.user) == {}  # type: ignore[arg-type]
    for code in REGISTRY:
        assert services.scope_for(actor, code) is None
        assert services.has_permission(actor, code, at_least=Scope.OWN) is False
        with pytest.raises(PermissionDeniedError):
            services.require_permission(actor, code, at_least=Scope.OWN)


def test_administrator_holds_configuration_rights_company_wide(admin_actor: Actor) -> None:
    assert services.effective_grants(admin_actor.user) == ADMINISTRATOR_GRANTS  # type: ignore[arg-type]
    assert services.require_permission(admin_actor, "role.assign", at_least=Scope.COMPANY)


def test_administrator_role_grants_no_task_permission() -> None:
    # D003: administrative rights are separate from visibility of task contents.
    assert not [code for code in ADMINISTRATOR_GRANTS if code.startswith("task")]
    assert not RoleGrant.objects.filter(
        role__key="administrator", permission_code__startswith="task"
    ).exists()


def test_administrator_role_in_database_matches_the_code_definition() -> None:
    stored = dict(
        RoleGrant.objects.filter(role__key="administrator", role__is_system=True).values_list(
            "permission_code", "scope"
        )
    )

    assert stored == {code: scope.value for code, scope in ADMINISTRATOR_GRANTS.items()}


def test_system_and_cli_actors_hold_no_permissions() -> None:
    for actor in (Actor.system("worker"), Actor.cli("os:root")):
        for code in REGISTRY:
            assert services.scope_for(actor, code) is None
        with pytest.raises(PermissionDeniedError):
            services.require_permission(actor, "role.manage", at_least=Scope.COMPANY)


def test_unknown_permission_code_fails_loudly(admin_actor: Actor) -> None:
    with pytest.raises(LookupError):
        services.has_permission(admin_actor, "role.manag", at_least=Scope.COMPANY)
    with pytest.raises(LookupError):
        services.require_permission(admin_actor, "task.read_everything", at_least=Scope.OWN)


def test_department_scoped_grant_does_not_satisfy_a_company_check(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    manager = make_user()
    _give(manager, _role("dept_auditor", audit__read=Scope.MANAGED_DEPARTMENTS), admin_actor)
    actor = Actor.for_user(manager)

    assert services.scope_for(actor, "audit.read") is Scope.MANAGED_DEPARTMENTS
    assert services.has_permission(actor, "audit.read", at_least=Scope.MANAGED_DEPARTMENTS)
    assert not services.has_permission(actor, "audit.read", at_least=Scope.COMPANY)
    with pytest.raises(PermissionDeniedError):
        services.require_permission(actor, "audit.read", at_least=Scope.COMPANY)


def test_several_roles_combine_and_the_widest_scope_wins(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    user = make_user()
    _give(user, _role("narrow", audit__read=Scope.MANAGED_DEPARTMENTS), admin_actor)
    _give(
        user,
        _role("wide", audit__read=Scope.COMPANY, user__create=Scope.MANAGED_DEPARTMENTS),
        admin_actor,
    )

    assert services.effective_grants(user) == {
        "audit.read": Scope.COMPANY,
        "user.create": Scope.MANAGED_DEPARTMENTS,
    }


def test_one_users_roles_do_not_leak_to_another(make_user: UserFactory, admin_actor: Actor) -> None:
    holder, other = make_user(), make_user()
    _give(holder, _role("auditor", audit__read=Scope.COMPANY), admin_actor)

    assert services.has_permission(Actor.for_user(holder), "audit.read", at_least=Scope.COMPANY)
    assert not services.has_permission(Actor.for_user(other), "audit.read", at_least=Scope.OWN)


def test_deactivated_user_loses_every_permission_at_once(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    user = make_user()
    _give(user, _role("auditor", audit__read=Scope.COMPANY), admin_actor)
    actor = Actor.for_user(user)  # an "open session": the object was loaded while active
    assert services.has_permission(actor, "audit.read", at_least=Scope.COMPANY)

    User.objects.filter(pk=user.pk).update(is_active=False, deactivated_at=timezone.now())

    assert services.effective_grants(user) == {}
    assert not services.has_permission(actor, "audit.read", at_least=Scope.OWN)


def test_revocation_applies_to_an_already_loaded_actor(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    # D020 / C1 req. 8: no re-login, no cache to expire.
    user = make_user()
    role = _role("auditor", audit__read=Scope.COMPANY)
    _give(user, role, admin_actor)
    actor = Actor.for_user(user)
    assert services.has_permission(actor, "audit.read", at_least=Scope.COMPANY)

    services.revoke_role(actor=admin_actor, user=user, role=role)

    assert not services.has_permission(actor, "audit.read", at_least=Scope.OWN)


def test_change_of_role_grants_applies_to_an_already_loaded_actor(
    make_user: UserFactory, admin_actor: Actor
) -> None:
    user = make_user()
    role = _role("auditor", audit__read=Scope.COMPANY)
    _give(user, role, admin_actor)
    actor = Actor.for_user(user)

    services.set_role_grants(
        actor=admin_actor, role=role, grants={"audit.read": Scope.MANAGED_DEPARTMENTS}
    )

    assert services.scope_for(actor, "audit.read") is Scope.MANAGED_DEPARTMENTS
    assert not services.has_permission(actor, "audit.read", at_least=Scope.COMPANY)
