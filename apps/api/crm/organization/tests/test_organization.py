"""S2: departments, memberships, managers and the reach of a manager's rights
(Q01, Q08, D018, D020)."""

from collections.abc import Callable
from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from crm.access import services as access
from crm.access.models import Role
from crm.access.permissions import (
    ADMINISTRATOR_GRANTS,
    DEPARTMENT_MANAGER_GRANTS,
    DEPARTMENT_MANAGER_ROLE_KEY,
)
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import STRONG_PASSWORD, Employee, EmployeeFactory, UserFactory
from crm.identity import auth, enrollment, users
from crm.identity.models import LoginChallenge, User
from crm.organization import services as org
from crm.organization.models import Department, DepartmentManager, DepartmentMembership

pytestmark = pytest.mark.django_db

ORIGIN = "http://127.0.0.1:3000"


@pytest.fixture
def sales(admin_actor: Actor) -> Department:
    return org.create_department(actor=admin_actor, name="Продажи")


@pytest.fixture
def support(admin_actor: Actor) -> Department:
    return org.create_department(actor=admin_actor, name="Поддержка")


@pytest.fixture
def manager(make_employee: EmployeeFactory, admin_actor: Actor, sales: Department) -> Employee:
    """Manages Sales (and belongs to it)."""
    boss = make_employee("olga.manager")
    org.add_member(actor=admin_actor, department_id=sales.pk, user_id=boss.user.pk)
    org.add_manager(actor=admin_actor, department_id=sales.pk, user_id=boss.user.pk)
    return boss


def holds_manager_role(user: User) -> bool:
    return user.role_links.filter(role__key=DEPARTMENT_MANAGER_ROLE_KEY).exists()


def sign_in(employee: Employee) -> APIClient:
    client = APIClient()
    client.post(
        "/api/v1/auth/login",
        {"login": employee.user.crm_login, "password": STRONG_PASSWORD},
        format="json",
        headers={"Origin": ORIGIN},
    )
    challenge = LoginChallenge.objects.filter(user=employee.user).latest("created_at")
    auth.decide_challenge(
        challenge_id=challenge.pk, telegram_user_id=employee.telegram_user_id, approve=True
    )
    assert (
        client.post("/api/v1/auth/login/complete", headers={"Origin": ORIGIN}).json()["state"]
        == "authenticated"
    )
    return client


def call(client: APIClient, method: str, path: str, data: object = None):  # type: ignore[no-untyped-def]
    return getattr(client, method)(path, data, format="json", headers={"Origin": ORIGIN})


# --- Catalogue --------------------------------------------------------------


def test_built_in_roles_match_the_catalogue(administrator: User, manager: Employee) -> None:
    assert access.effective_grants(administrator) == ADMINISTRATOR_GRANTS
    assert access.effective_grants(manager.user) == DEPARTMENT_MANAGER_GRANTS
    # A manager configures nothing company-wide and cannot touch roles.
    assert "department.manage" not in DEPARTMENT_MANAGER_GRANTS
    assert not any(code.startswith("role.") for code in DEPARTMENT_MANAGER_GRANTS)


# --- Departments ------------------------------------------------------------


def test_department_names_are_unique_ignoring_case(admin_actor: Actor, sales: Department) -> None:
    with pytest.raises(DomainError) as error:
        org.create_department(actor=admin_actor, name="  продажи ")

    assert error.value.code == "department_name_taken"
    with pytest.raises(DomainError):
        org.create_department(actor=admin_actor, name="   ")
    assert AuditEvent.objects.filter(action="department.created").count() == 1


def test_rename_is_audited_with_both_names(admin_actor: Actor, sales: Department) -> None:
    org.rename_department(actor=admin_actor, department_id=sales.pk, name="Отдел продаж")

    event = AuditEvent.objects.get(action="department.renamed")
    assert event.metadata == {"before": "Продажи", "after": "Отдел продаж"}


@pytest.mark.parametrize(
    "change",
    [
        lambda a, d, u: org.create_department(actor=a, name="Новый"),
        lambda a, d, u: org.rename_department(actor=a, department_id=d.pk, name="Другое"),
        lambda a, d, u: org.set_department_active(actor=a, department_id=d.pk, active=False),
        lambda a, d, u: org.add_member(actor=a, department_id=d.pk, user_id=u.pk),
        lambda a, d, u: org.remove_member(actor=a, department_id=d.pk, user_id=u.pk),
        lambda a, d, u: org.set_primary_department(actor=a, user_id=u.pk, department_id=d.pk),
        lambda a, d, u: org.add_manager(actor=a, department_id=d.pk, user_id=u.pk),
        lambda a, d, u: org.remove_manager(actor=a, department_id=d.pk, user_id=u.pk),
    ],
)
def test_only_an_administrator_changes_the_organization(
    change: Callable[[Actor, Department, User], object],
    sales: Department,
    manager: Employee,
    employee: Employee,
) -> None:
    # Not even the department's own manager may change who belongs to it or manages it.
    before = (
        DepartmentMembership.objects.count(),
        DepartmentManager.objects.count(),
        Department.objects.count(),
    )
    for actor in (
        Actor.for_user(manager.user),
        Actor.for_user(employee.user),
        Actor.system("worker"),
        Actor.cli("os:root"),
    ):
        with pytest.raises(PermissionDeniedError):
            change(actor, sales, employee.user)

    sales.refresh_from_db()
    assert sales.is_active
    assert sales.name == "Продажи"
    assert before == (
        DepartmentMembership.objects.count(),
        DepartmentManager.objects.count(),
        Department.objects.count(),
    )


# --- Memberships and the primary department (Q01) ---------------------------


def test_first_department_becomes_primary_and_later_ones_do_not(
    admin_actor: Actor, sales: Department, support: Department, employee: Employee
) -> None:
    first = org.add_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    second = org.add_member(actor=admin_actor, department_id=support.pk, user_id=employee.user.pk)
    again = org.add_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)

    assert (first.is_primary, second.is_primary) == (True, False)
    assert again.pk == first.pk
    assert DepartmentMembership.objects.filter(user=employee.user).count() == 2


def test_primary_department_moves_only_by_an_explicit_audited_action(
    admin_actor: Actor, sales: Department, support: Department, employee: Employee
) -> None:
    org.add_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    org.add_member(actor=admin_actor, department_id=support.pk, user_id=employee.user.pk)

    org.set_primary_department(
        actor=admin_actor, user_id=employee.user.pk, department_id=support.pk
    )

    primary = DepartmentMembership.objects.get(user=employee.user, is_primary=True)
    assert primary.department == support
    event = AuditEvent.objects.get(action="department.primary_changed")
    assert event.metadata == {"before": str(sales.pk), "after": str(support.pk)}


def test_primary_must_be_one_of_the_employees_departments(
    admin_actor: Actor, sales: Department, support: Department, employee: Employee
) -> None:
    org.add_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)

    with pytest.raises(DomainError) as error:
        org.set_primary_department(
            actor=admin_actor, user_id=employee.user.pk, department_id=support.pk
        )

    assert error.value.code == "not_a_member"


def test_primary_department_is_never_replaced_silently(
    admin_actor: Actor, sales: Department, support: Department, employee: Employee
) -> None:
    org.add_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    org.add_member(actor=admin_actor, department_id=support.pk, user_id=employee.user.pk)

    with pytest.raises(DomainError) as error:
        org.remove_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    assert error.value.code == "primary_department_required"

    # The only department may be left; the employee then has none.
    assert org.remove_member(actor=admin_actor, department_id=support.pk, user_id=employee.user.pk)
    assert org.remove_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    assert not org.remove_member(
        actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk
    )


def test_database_allows_one_primary_department_per_employee(
    admin_actor: Actor, sales: Department, support: Department, employee: Employee
) -> None:
    org.add_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)

    with pytest.raises(IntegrityError), transaction.atomic():
        DepartmentMembership.objects.create(user=employee.user, department=support, is_primary=True)


def test_closed_department_and_deactivated_employee_take_no_new_links(
    admin_actor: Actor, sales: Department, support: Department, employee: Employee
) -> None:
    org.set_department_active(actor=admin_actor, department_id=support.pk, active=False)
    with pytest.raises(DomainError) as closed:
        org.add_member(actor=admin_actor, department_id=support.pk, user_id=employee.user.pk)
    assert closed.value.code == "department_closed"

    users.deactivate_user(actor=admin_actor, user=employee.user)
    for attempt in (org.add_member, org.add_manager):
        with pytest.raises(DomainError) as inactive:
            attempt(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
        assert inactive.value.code == "user_inactive"


def test_department_cannot_be_closed_while_it_is_somebodys_primary(
    admin_actor: Actor, sales: Department, employee: Employee
) -> None:
    org.add_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)

    with pytest.raises(DomainError) as error:
        org.set_department_active(actor=admin_actor, department_id=sales.pk, active=False)

    assert error.value.code == "department_is_primary"
    sales.refresh_from_db()
    assert sales.is_active


# --- Managers (Q08) ---------------------------------------------------------


def test_first_manager_is_designated_and_the_designation_moves_explicitly(
    admin_actor: Actor, sales: Department, manager: Employee, employee: Employee
) -> None:
    first = DepartmentManager.objects.get(department=sales, user=manager.user)
    second = org.add_manager(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    assert (first.is_designated, second.is_designated) == (True, False)

    org.add_manager(
        actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk, designated=True
    )

    designated = DepartmentManager.objects.filter(department=sales, is_designated=True)
    assert [link.user for link in designated] == [employee.user]


def test_designated_manager_is_never_dropped_silently(
    admin_actor: Actor, sales: Department, manager: Employee, employee: Employee
) -> None:
    org.add_manager(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)

    with pytest.raises(DomainError) as error:
        org.remove_manager(actor=admin_actor, department_id=sales.pk, user_id=manager.user.pk)
    assert error.value.code == "designated_manager_required"

    assert org.remove_manager(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    # The last manager may go; the department then has none.
    assert org.remove_manager(actor=admin_actor, department_id=sales.pk, user_id=manager.user.pk)


def test_database_allows_one_designated_manager_per_department(
    sales: Department, manager: Employee, employee: Employee
) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        DepartmentManager.objects.create(department=sales, user=employee.user, is_designated=True)


def test_manager_role_follows_the_fact_of_managing(
    admin_actor: Actor, sales: Department, support: Department, employee: Employee
) -> None:
    assert not holds_manager_role(employee.user)

    org.add_manager(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    org.add_manager(actor=admin_actor, department_id=support.pk, user_id=employee.user.pk)
    assert holds_manager_role(employee.user)

    org.remove_manager(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    assert holds_manager_role(employee.user)  # still manages Support

    org.remove_manager(actor=admin_actor, department_id=support.pk, user_id=employee.user.pk)
    assert not holds_manager_role(employee.user)
    assert access.effective_grants(employee.user) == {}


def test_belonging_to_a_department_gives_no_rights(
    admin_actor: Actor, sales: Department, employee: Employee
) -> None:
    org.add_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)

    assert access.effective_grants(employee.user) == {}
    with pytest.raises(PermissionDeniedError):
        org.visible_departments(actor=Actor.for_user(employee.user))


# --- The reach of a manager's rights ----------------------------------------


def test_managed_scope_is_exactly_the_managed_departments(
    manager: Employee, sales: Department, support: Department
) -> None:
    actor = Actor.for_user(manager.user)

    scope = access.department_scope(actor, "user.read")

    assert not scope.company
    assert scope.department_ids == frozenset({sales.pk})
    assert scope.covers(sales.pk)
    assert not scope.covers(support.pk)
    assert not scope.covers(None)
    access.require_in_department(actor, "user.read", sales.pk)
    with pytest.raises(PermissionDeniedError):
        access.require_in_department(actor, "user.read", support.pk)


def test_manager_sees_only_managed_departments_and_their_people(
    admin_actor: Actor,
    manager: Employee,
    sales: Department,
    support: Department,
    make_employee: EmployeeFactory,
) -> None:
    in_sales = make_employee("in.sales")
    in_support = make_employee("in.support")
    in_both = make_employee("in.both")
    org.add_member(actor=admin_actor, department_id=sales.pk, user_id=in_sales.user.pk)
    org.add_member(actor=admin_actor, department_id=support.pk, user_id=in_support.user.pk)
    org.add_member(actor=admin_actor, department_id=support.pk, user_id=in_both.user.pk)
    org.add_member(actor=admin_actor, department_id=sales.pk, user_id=in_both.user.pk)
    actor = Actor.for_user(manager.user)

    assert list(org.visible_departments(actor=actor)) == [sales]
    logins = set(users.list_users(actor=actor).values_list("crm_login", flat=True))
    assert logins == {"olga.manager", "in.sales", "in.both"}


def test_manager_creates_employees_only_in_a_managed_department(
    manager: Employee, sales: Department, support: Department
) -> None:
    actor = Actor.for_user(manager.user)

    created = users.provision_user(
        actor=actor, crm_login="new.seller", display_name="Новый продавец", department_id=sales.pk
    )

    membership = DepartmentMembership.objects.get(user=created.user)
    assert (membership.department, membership.is_primary) == (sales, True)
    for department_id in (support.pk, None, uuid4()):
        with pytest.raises(PermissionDeniedError):
            users.provision_user(
                actor=actor, crm_login="xx1", display_name="X", department_id=department_id
            )
    assert not User.objects.filter(crm_login="xx1").exists()


def test_manager_issues_binding_codes_only_for_their_people(
    admin_actor: Actor, manager: Employee, sales: Department, make_user: UserFactory
) -> None:
    actor = Actor.for_user(manager.user)
    own = users.provision_user(
        actor=actor, crm_login="own.one", display_name="Свой", department_id=sales.pk
    )
    stranger = make_user("stranger")

    assert users.reissue_binding_token(actor=actor, user=own.user).value
    with pytest.raises(PermissionDeniedError):
        enrollment.issue_token(actor=actor, user=stranger)


def test_manager_cannot_deactivate_or_promote(manager: Employee, admin_actor: Actor) -> None:
    actor = Actor.for_user(manager.user)
    seller = users.provision_user(
        actor=actor,
        crm_login="seller",
        display_name="S",
        department_id=next(iter(access.managed_department_ids(manager.user))),
    ).user

    with pytest.raises(PermissionDeniedError):
        users.deactivate_user(actor=actor, user=seller)
    with pytest.raises(PermissionDeniedError):
        access.assign_role(actor=actor, user=seller, role=Role.objects.get(key="administrator"))


def test_losing_the_department_removes_the_reach_at_once(
    admin_actor: Actor, manager: Employee, sales: Department
) -> None:
    # D020: no new login is needed for the change to apply.
    actor = Actor.for_user(manager.user)
    version = User.objects.get(pk=manager.user.pk).permissions_version
    assert users.list_users(actor=actor).exists()

    org.remove_manager(actor=admin_actor, department_id=sales.pk, user_id=manager.user.pk)

    with pytest.raises(PermissionDeniedError):
        users.list_users(actor=actor)
    assert User.objects.get(pk=manager.user.pk).permissions_version > version


def test_closed_department_gives_its_manager_no_reach(
    admin_actor: Actor, manager: Employee, sales: Department
) -> None:
    org.remove_member(actor=admin_actor, department_id=sales.pk, user_id=manager.user.pk)
    org.set_department_active(actor=admin_actor, department_id=sales.pk, active=False)

    assert access.managed_department_ids(manager.user) == frozenset()
    with pytest.raises(PermissionDeniedError):
        org.visible_departments(actor=Actor.for_user(manager.user))


def test_deactivated_manager_has_no_reach(
    admin_actor: Actor, manager: Employee, sales: Department
) -> None:
    users.deactivate_user(actor=admin_actor, user=manager.user)

    assert access.managed_department_ids(manager.user) == frozenset()
    assert not access.department_scope(Actor.for_user(manager.user), "user.read")


# --- HTTP -------------------------------------------------------------------


def test_departments_api_needs_a_session_and_rights(employee: Employee, sales: Department) -> None:
    assert APIClient().get("/api/v1/departments").status_code == 401

    client = sign_in(employee)
    assert client.get("/api/v1/departments").status_code == 403
    assert call(client, "post", "/api/v1/departments", {"name": "Свой отдел"}).status_code == 403
    assert not Department.objects.filter(name="Свой отдел").exists()


def test_administrator_manages_departments_over_http(
    administrator: User, employee: Employee
) -> None:
    User.objects.filter(pk=administrator.pk).update(
        telegram_user_id=424242, telegram_bound_at=administrator.created_at
    )
    client = sign_in(Employee(administrator, STRONG_PASSWORD, 424242))

    created = call(client, "post", "/api/v1/departments", {"name": "Продажи"})
    assert created.status_code == 201
    department_id = created.json()["id"]
    base = f"/api/v1/departments/{department_id}"

    member = call(client, "post", f"{base}/members", {"user_id": str(employee.user.pk)})
    assert member.json()["members"] == [
        {
            "id": str(employee.user.pk),
            "crm_login": "anna.petrova",
            "display_name": employee.user.display_name,
            "is_active": True,
            "is_primary": True,
        }
    ]
    boss = call(client, "post", f"{base}/managers", {"user_id": str(employee.user.pk)})
    assert boss.json()["managers"][0]["is_designated"] is True

    listed = client.get("/api/v1/users").json()["results"]
    anna = next(row for row in listed if row["crm_login"] == "anna.petrova")
    assert anna["departments"] == [
        {"id": department_id, "name": "Продажи", "is_primary": True, "is_manager": True}
    ]

    duplicate = call(client, "post", "/api/v1/departments", {"name": "продажи"})
    assert duplicate.status_code == 400
    assert duplicate.json()["error"]["code"] == "department_name_taken"
    renamed = call(client, "patch", base, {"name": "Отдел продаж"})
    assert renamed.json()["name"] == "Отдел продаж"
    closing = call(client, "patch", base, {"is_active": False})
    assert closing.json()["error"]["code"] == "department_is_primary"

    assert call(client, "delete", f"{base}/managers/{employee.user.pk}").json()["managers"] == []
    assert call(client, "delete", f"{base}/members/{employee.user.pk}").json()["members"] == []
    assert call(client, "patch", base, {"is_active": False}).json()["is_active"] is False
    unknown = call(client, "patch", f"/api/v1/departments/{uuid4()}", {"name": "X"})
    assert unknown.status_code == 404


def test_manager_over_http_sees_own_department_and_cannot_change_it(
    manager: Employee, sales: Department, support: Department, employee: Employee
) -> None:
    client = sign_in(manager)

    listed = client.get("/api/v1/departments").json()["results"]
    assert [row["name"] for row in listed] == ["Продажи"]

    # A department outside the manager's reach does not exist for them...
    foreign = call(
        client,
        "post",
        f"/api/v1/departments/{support.pk}/members",
        {"user_id": str(employee.user.pk)},
    )
    assert foreign.status_code == 404
    # ...and their own they may see but not rearrange.
    own = call(
        client,
        "post",
        f"/api/v1/departments/{sales.pk}/members",
        {"user_id": str(employee.user.pk)},
    )
    assert own.status_code == 403
    assert not DepartmentMembership.objects.filter(user=employee.user).exists()

    created = call(
        client,
        "post",
        "/api/v1/users",
        {"crm_login": "new.seller", "display_name": "Продавец", "department_id": str(sales.pk)},
    )
    assert created.status_code == 201
    elsewhere = call(
        client,
        "post",
        "/api/v1/users",
        {"crm_login": "xx1", "display_name": "X", "department_id": str(support.pk)},
    )
    assert elsewhere.status_code == 403
