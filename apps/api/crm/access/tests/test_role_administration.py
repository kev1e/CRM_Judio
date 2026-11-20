"""Who may administer roles, and what every change leaves behind (D032-C1, req. 9)."""

from collections.abc import Callable

import pytest
from django.utils import timezone

from crm.access import services
from crm.access.models import Role, RoleGrant, UserRole
from crm.access.permissions import Scope
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import UserFactory
from crm.identity.models import User

pytestmark = pytest.mark.django_db


def _version(user: User) -> int:
    return User.objects.values_list("permissions_version", flat=True).get(pk=user.pk)


def _audit(action: str) -> list[AuditEvent]:
    return list(AuditEvent.objects.filter(action=action).order_by("occurred_at", "id"))


@pytest.fixture
def custom_role(admin_actor: Actor) -> Role:
    role = services.create_role(actor=admin_actor, key="auditor", name="Аудитор")
    services.set_role_grants(actor=admin_actor, role=role, grants={"audit.read": Scope.COMPANY})
    return role


# --- Negative authorization: everyone but an administrator is refused ---------


@pytest.fixture(params=["no_roles", "holder_of_custom_role", "system", "cli"])
def outsider(
    request: pytest.FixtureRequest, make_user: UserFactory, admin_actor: Actor, custom_role: Role
) -> Actor:
    if request.param == "system":
        return Actor.system("worker")
    if request.param == "cli":
        return Actor.cli("os:someone")
    user = make_user()
    if request.param == "holder_of_custom_role":
        services.assign_role(actor=admin_actor, user=user, role=custom_role)
    return Actor.for_user(user)


def test_outsider_cannot_administer_roles(
    outsider: Actor, make_user: UserFactory, custom_role: Role, administrator: User
) -> None:
    victim = make_user()
    admin_role = Role.objects.get(key="administrator")
    events_before = AuditEvent.objects.count()
    attempts: list[Callable[[], object]] = [
        lambda: services.create_role(actor=outsider, key="mine", name="Mine"),
        lambda: services.set_role_grants(actor=outsider, role=custom_role, grants={}),
        lambda: services.delete_role(actor=outsider, role=custom_role),
        lambda: services.assign_role(actor=outsider, user=victim, role=custom_role),
        lambda: services.assign_role(actor=outsider, user=victim, role=admin_role),
        lambda: services.revoke_role(actor=outsider, user=administrator, role=admin_role),
    ]

    for attempt in attempts:
        with pytest.raises(PermissionDeniedError):
            attempt()

    assert not Role.objects.filter(key="mine").exists()
    assert not UserRole.objects.filter(user=victim).exists()
    assert UserRole.objects.filter(user=administrator, role=admin_role).exists()
    assert AuditEvent.objects.count() == events_before


def test_user_cannot_make_themselves_administrator(
    make_user: UserFactory, admin_actor: Actor, custom_role: Role
) -> None:
    user = make_user()
    services.assign_role(actor=admin_actor, user=user, role=custom_role)

    with pytest.raises(PermissionDeniedError):
        services.assign_role(
            actor=Actor.for_user(user), user=user, role=Role.objects.get(key="administrator")
        )

    assert not services.has_permission(Actor.for_user(user), "role.assign", at_least=Scope.COMPANY)


def test_deactivated_administrator_can_no_longer_administer(
    administrator: User, admin_actor: Actor, make_user: UserFactory
) -> None:
    User.objects.filter(pk=administrator.pk).update(is_active=False, deactivated_at=timezone.now())

    with pytest.raises(PermissionDeniedError):
        services.create_role(actor=admin_actor, key="late", name="Late")


# --- Roles -------------------------------------------------------------------


def test_create_role_is_audited(admin_actor: Actor, administrator: User) -> None:
    role = services.create_role(actor=admin_actor, key=" Reports ", name=" Отчёты ")

    assert (role.key, role.name, role.is_system) == ("reports", "Отчёты", False)
    (event,) = _audit("role.created")
    assert event.actor == administrator
    assert event.entity_id == str(role.pk)
    assert event.metadata == {"key": "reports"}


@pytest.mark.parametrize("key", ["", "1abc", "has space", "x", "ROLE-1", "a" * 64])
def test_malformed_role_key_is_refused(admin_actor: Actor, key: str) -> None:
    with pytest.raises(DomainError) as error:
        services.create_role(actor=admin_actor, key=key, name="X")
    assert error.value.code == "invalid_role_key"


def test_duplicate_role_key_is_refused(admin_actor: Actor, custom_role: Role) -> None:
    with pytest.raises(DomainError) as error:
        services.create_role(actor=admin_actor, key="auditor", name="Again")
    assert error.value.code == "role_key_taken"
    assert len(_audit("role.created")) == 1


def test_changing_grants_bumps_holders_and_records_before_and_after(
    admin_actor: Actor, custom_role: Role, make_user: UserFactory
) -> None:
    holder, bystander = make_user(), make_user()
    services.assign_role(actor=admin_actor, user=holder, role=custom_role)
    holder_version, bystander_version = _version(holder), _version(bystander)

    services.set_role_grants(
        actor=admin_actor,
        role=custom_role,
        grants={"audit.read": Scope.MANAGED_DEPARTMENTS, "user.create": Scope.COMPANY},
    )

    assert _version(holder) == holder_version + 1
    assert _version(bystander) == bystander_version
    event = _audit("role.grants_changed")[-1]
    assert event.metadata == {
        "key": "auditor",
        "before": {"audit.read": "company"},
        "after": {"audit.read": "managed_departments", "user.create": "company"},
        "holders": 1,
    }


def test_setting_identical_grants_changes_nothing(
    admin_actor: Actor, custom_role: Role, make_user: UserFactory
) -> None:
    holder = make_user()
    services.assign_role(actor=admin_actor, user=holder, role=custom_role)
    version, events = _version(holder), AuditEvent.objects.count()

    services.set_role_grants(
        actor=admin_actor, role=custom_role, grants={"audit.read": Scope.COMPANY}
    )

    assert _version(holder) == version
    assert AuditEvent.objects.count() == events


@pytest.mark.parametrize(
    ("grants", "code"),
    [
        ({"task.read_all": Scope.COMPANY}, "unknown_permission"),
        ({"user.update": Scope.OWN}, "invalid_scope"),
        ({"audit.read": Scope.OWN}, "invalid_scope"),
        ({"audit.read": "galaxy"}, "invalid_scope"),
        # Administrator-only powers (Q28, REC-01) cannot be put into a custom role.
        ({"user.email.verify": Scope.COMPANY}, "permission_not_grantable"),
        ({"user.recovery.manage": Scope.COMPANY}, "permission_not_grantable"),
        ({"role.assign": Scope.COMPANY}, "permission_not_grantable"),
        ({"role.manage": Scope.COMPANY}, "permission_not_grantable"),
    ],
)
def test_invalid_grants_are_refused_and_leave_the_role_untouched(
    admin_actor: Actor, custom_role: Role, grants: dict[str, Scope], code: str
) -> None:
    with pytest.raises(DomainError) as error:
        services.set_role_grants(actor=admin_actor, role=custom_role, grants=grants)

    assert error.value.code == code
    assert list(custom_role.grants.values_list("permission_code", "scope")) == [
        ("audit.read", "company")
    ]


def test_built_in_role_cannot_be_changed_or_removed(admin_actor: Actor) -> None:
    admin_role = Role.objects.get(key="administrator")
    grants_before = RoleGrant.objects.filter(role=admin_role).count()

    attempts: list[Callable[[], object]] = [
        lambda: services.set_role_grants(actor=admin_actor, role=admin_role, grants={}),
        lambda: services.delete_role(actor=admin_actor, role=admin_role),
    ]
    for attempt in attempts:
        with pytest.raises(DomainError) as error:
            attempt()
        assert error.value.code == "system_role_immutable"

    assert RoleGrant.objects.filter(role=admin_role).count() == grants_before


def test_role_in_use_cannot_be_deleted_and_unused_one_can(
    admin_actor: Actor, custom_role: Role, make_user: UserFactory
) -> None:
    holder = make_user()
    services.assign_role(actor=admin_actor, user=holder, role=custom_role)

    with pytest.raises(DomainError) as error:
        services.delete_role(actor=admin_actor, role=custom_role)
    assert error.value.code == "role_in_use"

    services.revoke_role(actor=admin_actor, user=holder, role=custom_role)
    services.delete_role(actor=admin_actor, role=custom_role)

    assert not Role.objects.filter(key="auditor").exists()
    (event,) = _audit("role.deleted")
    assert event.metadata == {"key": "auditor", "grants": {"audit.read": "company"}}


# --- Assignment --------------------------------------------------------------


def test_assign_and_revoke_bump_version_and_are_audited(
    admin_actor: Actor, administrator: User, custom_role: Role, make_user: UserFactory
) -> None:
    user = make_user()
    version = _version(user)

    assert services.assign_role(actor=admin_actor, user=user, role=custom_role) is True
    assert _version(user) == version + 1
    link = UserRole.objects.get(user=user, role=custom_role)
    assert link.granted_by == administrator
    assigned = _audit("role.assigned")[-1]
    assert (assigned.entity_id, assigned.metadata) == (str(user.pk), {"role": "auditor"})
    assert assigned.actor == administrator

    assert services.revoke_role(actor=admin_actor, user=user, role=custom_role) is True
    assert _version(user) == version + 2
    (revoked,) = _audit("role.revoked")
    assert (revoked.entity_id, revoked.metadata) == (str(user.pk), {"role": "auditor"})


def test_repeating_assignment_or_revocation_is_a_no_op(
    admin_actor: Actor, custom_role: Role, make_user: UserFactory
) -> None:
    user = make_user()
    services.assign_role(actor=admin_actor, user=user, role=custom_role)
    version, events = _version(user), AuditEvent.objects.count()

    assert services.assign_role(actor=admin_actor, user=user, role=custom_role) is False
    assert (_version(user), AuditEvent.objects.count()) == (version, events)

    services.revoke_role(actor=admin_actor, user=user, role=custom_role)
    version, events = _version(user), AuditEvent.objects.count()
    assert services.revoke_role(actor=admin_actor, user=user, role=custom_role) is False
    assert (_version(user), AuditEvent.objects.count()) == (version, events)


def test_deactivated_user_cannot_receive_a_role(
    admin_actor: Actor, custom_role: Role, make_user: UserFactory
) -> None:
    user = make_user()
    User.objects.filter(pk=user.pk).update(is_active=False, deactivated_at=timezone.now())

    with pytest.raises(DomainError) as error:
        services.assign_role(actor=admin_actor, user=user, role=custom_role)
    assert error.value.code == "user_inactive"


def test_last_active_administrator_cannot_lose_the_role(
    admin_actor: Actor, administrator: User, make_user: UserFactory
) -> None:
    admin_role = Role.objects.get(key="administrator")

    with pytest.raises(DomainError) as error:
        services.revoke_role(actor=admin_actor, user=administrator, role=admin_role)
    assert error.value.code == "last_administrator"

    # A deactivated second administrator does not count as a remaining one.
    second = make_user()
    services.assign_role(actor=admin_actor, user=second, role=admin_role)
    User.objects.filter(pk=second.pk).update(is_active=False, deactivated_at=timezone.now())
    with pytest.raises(DomainError):
        services.revoke_role(actor=admin_actor, user=administrator, role=admin_role)

    # With another active administrator the role can be handed over.
    third = make_user()
    services.assign_role(actor=admin_actor, user=third, role=admin_role)
    assert services.revoke_role(actor=Actor.for_user(third), user=administrator, role=admin_role)
    assert not services.has_permission(admin_actor, "role.assign", at_least=Scope.COMPANY)
