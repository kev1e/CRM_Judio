"""Projects and cross-department invitations (D003, D004, D018, Q10, Q29).

The exit criterion of S4: the invitation flow works and project membership
gives no access to tasks."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from crm.access import services as access
from crm.access.models import Role
from crm.access.permissions import (
    ADMINISTRATOR_GRANTS,
    BASELINE_GRANTS,
    DEPARTMENT_MANAGER_GRANTS,
    Scope,
)
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import STRONG_PASSWORD, Employee
from crm.identity import users
from crm.organization import services as org
from crm.projects import services
from crm.projects.models import InvitationState, Project, ProjectInvitation, ProjectMember
from crm.tasks import services as tasks
from crm.tasks.tests.test_tasks import World, make_task, uid, world  # noqa: F401
from crm.tasks.tests.test_tasks_api import call, sign_in

pytestmark = pytest.mark.django_db

# World: Sales — manager Olga, employees Anna and Boris. Support — manager Pavel,
# employees Vera and Zoya (superuser role). Boris is in Sales only.


def project(world: World, name: str = "Запуск продукта") -> Project:  # noqa: F811
    return services.create_project(actor=world.olga, name=name, department_id=world.sales.pk)


def invite(world: World, target: Project, who: Actor) -> ProjectInvitation:  # noqa: F811
    joined = services.add_participant(
        actor=world.olga, project_id=target.pk, user_id=uid(who), department_id=world.support.pk
    )
    assert joined.member is None
    assert joined.invitation is not None
    return joined.invitation


def code(error: pytest.ExceptionInfo[DomainError]) -> str:
    return error.value.code


def test_grants() -> None:
    for permission in ("project.manage", "project.invitation.approve"):
        assert DEPARTMENT_MANAGER_GRANTS[permission] is Scope.MANAGED_DEPARTMENTS
        assert permission not in BASELINE_GRANTS
        # The administrator role configures the CRM; it does not run projects.
        assert permission not in ADMINISTRATOR_GRANTS
        assert (
            Role.objects.get(key="department_manager")
            .grants.filter(permission_code=permission, scope="managed_departments")
            .exists()
        )
        assert (
            not Role.objects.get(key="administrator")
            .grants.filter(permission_code=permission)
            .exists()
        )


# --- Projects ---------------------------------------------------------------


def test_manager_creates_a_project_for_a_managed_department(world: World) -> None:  # noqa: F811
    created = services.create_project(
        actor=world.olga, name="  Запуск   продукта ", department_id=world.sales.pk
    )
    assert created.name == "Запуск продукта"
    assert created.owning_department == world.sales
    assert AuditEvent.objects.get(action="project.created").entity_id == str(created.pk)

    for actor, department in (
        (world.olga, world.support),  # another department
        (world.anna, world.sales),  # an employee
        (world.admin, world.sales),  # the administrator
        (world.zoya, world.support),  # the read-only superuser
    ):
        with pytest.raises(PermissionDeniedError):
            services.create_project(actor=actor, name="Чужой", department_id=department.pk)
    with pytest.raises(DomainError) as error:
        services.create_project(
            actor=world.olga, name="запуск продукта", department_id=world.sales.pk
        )
    assert code(error) == "project_name_taken"
    with pytest.raises(DomainError) as error:
        services.create_project(actor=world.olga, name="  ", department_id=world.sales.pk)
    assert code(error) == "invalid_project_name"
    assert Project.objects.count() == 1


def test_own_employee_is_added_directly(world: World) -> None:  # noqa: F811
    target = project(world)

    joined = services.add_participant(
        actor=world.olga,
        project_id=target.pk,
        user_id=uid(world.anna),
        department_id=world.sales.pk,
    )

    assert joined.invitation is None
    assert joined.member is not None
    assert joined.member.participation_department == world.sales
    assert not ProjectInvitation.objects.exists()
    event = AuditEvent.objects.get(action="project.member_added")
    assert event.metadata["via"] == "direct"
    with pytest.raises(DomainError) as error:
        services.add_participant(
            actor=world.olga,
            project_id=target.pk,
            user_id=uid(world.anna),
            department_id=world.sales.pk,
        )
    assert code(error) == "already_member"


# --- Invitations (D018, Q10) ------------------------------------------------


def test_employee_of_another_department_is_only_invited(world: World) -> None:  # noqa: F811
    target = project(world)

    invitation = invite(world, target, world.vera)

    assert invitation.state == InvitationState.PENDING
    assert invitation.participation_department == world.support
    # Until the approval: no membership, and the project is invisible to Vera.
    assert not ProjectMember.objects.exists()
    assert target not in services.visible_projects(world.vera)
    assert list(services.invitations_to_decide(world.pavel)) == [invitation]
    assert list(services.invitations_to_decide(world.olga)) == []
    with pytest.raises(DomainError) as error:
        invite(world, target, world.vera)
    assert code(error) == "already_invited"


def test_the_employees_manager_approves_and_only_then_membership_appears(
    world: World,  # noqa: F811
) -> None:
    target = project(world)
    invitation = invite(world, target, world.vera)

    member = services.approve_invitation(actor=world.pavel, invitation_id=invitation.pk)

    assert member.user == world.vera.user
    assert member.participation_department == world.support
    assert member.added_by == world.olga.user
    invitation.refresh_from_db()
    assert invitation.state == InvitationState.APPROVED
    assert invitation.decided_by == world.pavel.user
    assert target in services.visible_projects(world.vera)
    assert target in services.visible_projects(world.pavel)  # his employee takes part
    assert AuditEvent.objects.filter(action="project.invitation_approved").count() == 1
    with pytest.raises(DomainError) as error:
        services.approve_invitation(actor=world.pavel, invitation_id=invitation.pk)
    assert code(error) == "invitation_decided"


@pytest.mark.parametrize("who", ["olga", "anna", "vera", "admin", "zoya"])
def test_nobody_else_can_approve_or_decline(world: World, who: str) -> None:  # noqa: F811
    # Not the requester, not the invited employee herself, not the administrator,
    # not the superuser without the separate grant (Q29).
    target = project(world)
    invitation = invite(world, target, world.vera)
    actor: Actor = getattr(world, who)

    for operation in (services.approve_invitation, services.decline_invitation):
        with pytest.raises(DomainError) as error:
            operation(actor=actor, invitation_id=invitation.pk)
        assert code(error) == "invitation_not_found"

    invitation.refresh_from_db()
    assert invitation.state == InvitationState.PENDING
    assert not ProjectMember.objects.exists()


def test_superuser_approves_only_with_the_separate_grant(world: World) -> None:  # noqa: F811
    target = project(world)
    invitation = invite(world, target, world.vera)
    role = access.create_role(actor=world.admin, key="approver", name="Согласование")
    access.set_role_grants(
        actor=world.admin, role=role, grants={"project.invitation.approve": Scope.COMPANY}
    )
    assert world.zoya.user is not None
    access.assign_role(actor=world.admin, user=world.zoya.user, role=role)

    services.approve_invitation(actor=world.zoya, invitation_id=invitation.pk)

    assert ProjectMember.objects.filter(project=target, user=world.vera.user).exists()


def test_decline_grants_nothing_and_keeps_the_reason(world: World) -> None:  # noqa: F811
    target = project(world)
    invitation = invite(world, target, world.vera)

    services.decline_invitation(
        actor=world.pavel, invitation_id=invitation.pk, reason="  Занята до конца квартала "
    )

    invitation.refresh_from_db()
    assert invitation.state == InvitationState.DECLINED
    assert invitation.reason == "Занята до конца квартала"
    assert not ProjectMember.objects.exists()
    assert target not in services.visible_projects(world.vera)
    # The reason stays out of the audit log; a new invitation may be sent later.
    assert "квартала" not in str(list(AuditEvent.objects.values_list("metadata", flat=True)))
    invite(world, target, world.vera)


def test_requesting_side_cancels(world: World) -> None:  # noqa: F811
    target = project(world)
    invitation = invite(world, target, world.vera)
    for actor in (world.pavel, world.vera, world.anna):
        with pytest.raises(DomainError) as error:
            services.cancel_invitation(actor=actor, invitation_id=invitation.pk)
        assert code(error) == "invitation_not_found"

    services.cancel_invitation(actor=world.olga, invitation_id=invitation.pk)

    with pytest.raises(DomainError) as error:
        services.approve_invitation(actor=world.pavel, invitation_id=invitation.pk)
    assert code(error) == "invitation_decided"
    assert not ProjectMember.objects.exists()


def test_participation_department_must_be_the_employees_own(world: World) -> None:  # noqa: F811
    target = project(world)
    # Vera is not in Sales: naming Sales would let Olga skip the approval.
    with pytest.raises(DomainError) as error:
        services.add_participant(
            actor=world.olga,
            project_id=target.pk,
            user_id=uid(world.vera),
            department_id=world.sales.pk,
        )
    assert code(error) == "not_in_department"
    assert not ProjectMember.objects.exists()
    assert not ProjectInvitation.objects.exists()


def test_approval_rechecks_membership_and_account(world: World) -> None:  # noqa: F811
    target = project(world)
    left = invite(world, target, world.vera)
    org.add_member(actor=world.admin, department_id=world.sales.pk, user_id=uid(world.vera))
    org.set_primary_department(
        actor=world.admin, user_id=uid(world.vera), department_id=world.sales.pk
    )
    org.remove_member(actor=world.admin, department_id=world.support.pk, user_id=uid(world.vera))
    with pytest.raises(DomainError) as error:
        services.approve_invitation(actor=world.pavel, invitation_id=left.pk)
    assert code(error) == "not_in_department"

    other = project(world, "Второй")
    inactive = invite(world, other, world.zoya)
    assert world.zoya.user is not None
    users.deactivate_user(actor=world.admin, user=world.zoya.user)
    with pytest.raises(DomainError) as error:
        services.approve_invitation(actor=world.pavel, invitation_id=inactive.pk)
    assert code(error) == "not_in_department"
    assert not ProjectMember.objects.exists()


def test_manager_who_lost_the_department_cannot_decide(world: World) -> None:  # noqa: F811
    target = project(world)
    invitation = invite(world, target, world.vera)
    org.add_manager(
        actor=world.admin, department_id=world.support.pk, user_id=uid(world.zoya), designated=True
    )
    org.remove_manager(actor=world.admin, department_id=world.support.pk, user_id=uid(world.pavel))

    with pytest.raises(DomainError) as error:
        services.approve_invitation(actor=world.pavel, invitation_id=invitation.pk)
    assert code(error) == "invitation_not_found"


def test_manager_of_both_departments_adds_directly(world: World) -> None:  # noqa: F811
    # Olga also manages Support: she is the approving authority herself.
    org.add_manager(actor=world.admin, department_id=world.support.pk, user_id=uid(world.olga))
    target = project(world)
    joined = services.add_participant(
        actor=world.olga,
        project_id=target.pk,
        user_id=uid(world.vera),
        department_id=world.support.pk,
    )
    assert joined.member is not None


# --- Membership gives no task access (D003) ---------------------------------


def test_project_membership_shows_no_tasks(world: World) -> None:  # noqa: F811
    target = project(world)
    services.add_participant(
        actor=world.olga,
        project_id=target.pk,
        user_id=uid(world.anna),
        department_id=world.sales.pk,
    )
    services.add_participant(
        actor=world.olga,
        project_id=target.pk,
        user_id=uid(world.boris),
        department_id=world.sales.pk,
    )
    services.approve_invitation(
        actor=world.pavel, invitation_id=invite(world, target, world.vera).pk
    )
    task = make_task(world)  # a Sales task assigned to Anna

    # Fellow participants — from the same department and from another one — and
    # the other department's manager who now sees the project.
    for outsider in (world.boris, world.vera, world.pavel):
        assert target in services.visible_projects(outsider)
        with pytest.raises(DomainError) as error:
            tasks.get_task(outsider, task.pk)
        assert code(error) == "task_not_found"
        assert list(tasks.board(outsider, view="mine")) == []


# --- Seeing and running a project -------------------------------------------


def test_who_sees_a_project(world: World) -> None:  # noqa: F811
    target = project(world)
    services.add_participant(
        actor=world.olga,
        project_id=target.pk,
        user_id=uid(world.anna),
        department_id=world.sales.pk,
    )

    assert list(services.visible_projects(world.olga)) == [target]  # runs it
    assert list(services.visible_projects(world.anna)) == [target]  # takes part
    for outsider in (world.boris, world.pavel, world.vera, world.zoya, world.admin):
        assert list(services.visible_projects(outsider)) == []
    assert list(services.visible_projects(Actor.system("worker"))) == []


def test_only_the_owning_departments_manager_runs_the_project(world: World) -> None:  # noqa: F811
    target = project(world)
    services.add_participant(
        actor=world.olga,
        project_id=target.pk,
        user_id=uid(world.anna),
        department_id=world.sales.pk,
    )
    services.approve_invitation(
        actor=world.pavel, invitation_id=invite(world, target, world.vera).pk
    )

    # A participant and the other department's manager see it and cannot change it.
    for actor in (world.anna, world.pavel):
        for operation in (
            lambda actor=actor: services.rename_project(
                actor=actor, project_id=target.pk, name="Другое"
            ),
            lambda actor=actor: services.set_project_active(
                actor=actor, project_id=target.pk, active=False
            ),
            lambda actor=actor: services.add_participant(
                actor=actor,
                project_id=target.pk,
                user_id=uid(world.zoya),
                department_id=world.support.pk,
            ),
            lambda actor=actor: services.remove_participant(
                actor=actor, project_id=target.pk, user_id=uid(world.anna)
            ),
        ):
            with pytest.raises(PermissionDeniedError):
                operation()
    # Somebody who does not see it at all.
    with pytest.raises(DomainError) as error:
        services.rename_project(actor=world.boris, project_id=target.pk, name="Другое")
    assert code(error) == "project_not_found"
    assert Project.objects.get().name == "Запуск продукта"
    assert ProjectMember.objects.count() == 2


def test_remove_participant(world: World) -> None:  # noqa: F811
    target = project(world)
    services.add_participant(
        actor=world.olga,
        project_id=target.pk,
        user_id=uid(world.anna),
        department_id=world.sales.pk,
    )
    services.remove_participant(actor=world.olga, project_id=target.pk, user_id=uid(world.anna))
    assert list(services.visible_projects(world.anna)) == []
    with pytest.raises(DomainError) as error:
        services.remove_participant(actor=world.olga, project_id=target.pk, user_id=uid(world.anna))
    assert code(error) == "member_not_found"


def test_closing_a_project_cancels_waiting_invitations(world: World) -> None:  # noqa: F811
    target = project(world)
    invitation = invite(world, target, world.vera)

    services.set_project_active(actor=world.olga, project_id=target.pk, active=False)

    invitation.refresh_from_db()
    assert invitation.state == InvitationState.CANCELLED
    with pytest.raises(DomainError) as error:
        services.add_participant(
            actor=world.olga,
            project_id=target.pk,
            user_id=uid(world.anna),
            department_id=world.sales.pk,
        )
    assert code(error) == "project_closed"
    assert AuditEvent.objects.get(action="project.closed").metadata["cancelled_invitations"] == 1


def test_candidates_are_for_those_who_run_projects(world: World) -> None:  # noqa: F811
    logins = [user.crm_login for user in services.candidates(world.olga)]
    assert {"anna", "boris", "vera", "zoya", "olga", "pavel"} <= set(logins)
    for actor in (world.anna, world.admin, world.zoya):
        with pytest.raises(PermissionDeniedError):
            services.candidates(actor)


# --- HTTP -------------------------------------------------------------------


def test_api_invitation_flow(world: World) -> None:  # noqa: F811
    def client(actor: Actor) -> APIClient:
        assert actor.user is not None
        assert actor.user.telegram_user_id is not None
        return sign_in(
            Employee(
                user=actor.user,
                password=STRONG_PASSWORD,
                telegram_user_id=actor.user.telegram_user_id,
            )
        )

    olga, pavel, vera, anna = (client(a) for a in (world.olga, world.pavel, world.vera, world.anna))

    created = call(
        olga, "post", "/api/v1/projects", {"name": "Запуск", "department_id": str(world.sales.pk)}
    )
    assert created.status_code == 201
    project_id = created.json()["id"]
    assert created.json()["can_manage"] is True
    assert (
        call(
            anna, "post", "/api/v1/projects", {"name": "X", "department_id": str(world.sales.pk)}
        ).status_code
        == 403
    )

    candidates = call(olga, "get", "/api/v1/project-candidates")
    assert candidates.status_code == 200
    row = next(c for c in candidates.json()["results"] if c["id"] == str(uid(world.vera)))
    assert row["departments"] == [{"id": str(world.support.pk), "name": "Поддержка"}]
    assert set(row) == {"id", "name", "departments"}
    assert call(anna, "get", "/api/v1/project-candidates").status_code == 403

    direct = call(
        olga,
        "post",
        f"/api/v1/projects/{project_id}/members",
        {"user_id": str(uid(world.anna)), "department_id": str(world.sales.pk)},
    )
    assert (direct.status_code, direct.json()["outcome"]) == (200, "added")
    invited = call(
        olga,
        "post",
        f"/api/v1/projects/{project_id}/members",
        {"user_id": str(uid(world.vera)), "department_id": str(world.support.pk)},
    )
    assert (invited.status_code, invited.json()["outcome"]) == (200, "invited")
    (pending,) = invited.json()["project"]["pending_invitations"]
    assert [m["user"]["id"] for m in invited.json()["project"]["members"]] == [str(uid(world.anna))]

    # Anna takes part: she sees the project and its people, not the invitations.
    seen = call(anna, "get", "/api/v1/projects").json()
    assert seen["can_create"] is False
    assert seen["results"][0]["can_manage"] is False
    assert seen["results"][0]["pending_invitations"] == []
    # Vera is only invited: nothing yet. Olga cannot approve her own request.
    assert call(vera, "get", "/api/v1/projects").json()["results"] == []
    approve = f"/api/v1/project-invitations/{pending['id']}/approve"
    assert call(olga, "post", approve).status_code == 404
    assert call(vera, "post", approve).status_code == 404

    inbox = call(pavel, "get", "/api/v1/projects").json()["invitations_to_decide"]
    assert [(i["id"], i["project"]["name"], i["user"]["id"]) for i in inbox] == [
        (pending["id"], "Запуск", str(uid(world.vera)))
    ]
    assert call(pavel, "post", approve).status_code == 204
    assert call(pavel, "post", approve).status_code == 400
    assert [p["name"] for p in call(vera, "get", "/api/v1/projects").json()["results"]] == [
        "Запуск"
    ]
    assert call(pavel, "get", "/api/v1/projects").json()["invitations_to_decide"] == []

    assert call(pavel, "patch", f"/api/v1/projects/{project_id}", {"name": "Х"}).status_code == 403
    removed = call(olga, "delete", f"/api/v1/projects/{project_id}/members/{uid(world.vera)}")
    assert removed.status_code == 200
    assert call(vera, "get", "/api/v1/projects").json()["results"] == []
    closed = call(olga, "patch", f"/api/v1/projects/{project_id}", {"is_active": False})
    assert closed.json()["is_active"] is False
    assert call(olga, "patch", f"/api/v1/projects/{uuid4()}", {"name": "Х"}).status_code == 404
    assert APIClient().get("/api/v1/projects").status_code == 401
