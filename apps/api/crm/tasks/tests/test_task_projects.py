"""A task's optional project: a label chosen by the manager that changes nothing
about who sees the task (D003, D004)."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from crm.access.permissions import BASELINE_GRANTS, DEPARTMENT_MANAGER_GRANTS, Scope
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import STRONG_PASSWORD, Employee
from crm.projects import services as projects
from crm.projects.models import Project
from crm.tasks import policy, services
from crm.tasks.tests.test_tasks import World, make_task, reload, uid, world  # noqa: F401
from crm.tasks.tests.test_tasks_api import call, sign_in

pytestmark = pytest.mark.django_db


def sales_project(world: World, name: str = "Запуск") -> Project:  # noqa: F811
    return projects.create_project(actor=world.olga, name=name, department_id=world.sales.pk)


def support_project(world: World) -> Project:  # noqa: F811
    return projects.create_project(
        actor=world.pavel, name="Поддержка 2.0", department_id=world.support.pk
    )


def test_grant() -> None:
    assert "task.project" not in BASELINE_GRANTS
    assert DEPARTMENT_MANAGER_GRANTS["task.project"] is Scope.MANAGED_DEPARTMENTS


def test_task_is_created_in_a_project(world: World) -> None:  # noqa: F811
    target = sales_project(world)
    task = services.create_task(
        actor=world.olga,
        title="Лендинг",
        department_id=world.sales.pk,
        assignee_id=uid(world.anna),
        project_id=target.pk,
    )
    assert task.project == target
    assert make_task(world).project is None  # the project is optional


def test_manager_moves_a_task_between_projects_and_out(world: World) -> None:  # noqa: F811
    first, second = sales_project(world), sales_project(world, "Второй")
    task = make_task(world)

    services.change_project(actor=world.olga, task_id=task.pk, project_id=first.pk)
    services.change_project(actor=world.olga, task_id=task.pk, project_id=second.pk)
    services.change_project(actor=world.olga, task_id=task.pk, project_id=second.pk)  # no change
    services.change_project(actor=world.olga, task_id=task.pk, project_id=None)

    assert reload(task).project is None
    assert reload(task).row_version == 4
    events = AuditEvent.objects.filter(action="task.project_changed").order_by("occurred_at")
    assert [(e.metadata["before"], e.metadata["after"]) for e in events] == [
        (None, str(first.pk)),
        (str(first.pk), str(second.pk)),
        (str(second.pk), None),
    ]


def test_only_the_manager_chooses_the_project(world: World) -> None:  # noqa: F811
    target = sales_project(world)
    task = make_task(world)

    assert policy.actions(world.anna, task)["task.project"] is False
    for actor in (world.anna, world.zoya):  # the assignee, the read-only superuser
        with pytest.raises(PermissionDeniedError):
            services.change_project(actor=actor, task_id=task.pk, project_id=target.pk)
    for actor in (world.boris, world.pavel, world.admin):  # cannot see the task
        with pytest.raises(DomainError) as error:
            services.change_project(actor=actor, task_id=task.pk, project_id=target.pk)
        assert error.value.code == "task_not_found"
    assert reload(task).project is None


def test_project_must_be_open_and_visible_to_the_manager(world: World) -> None:  # noqa: F811
    foreign = support_project(world)  # Olga neither runs it nor has people in it
    closed = sales_project(world, "Закрытый")
    projects.set_project_active(actor=world.olga, project_id=closed.pk, active=False)
    task = make_task(world)

    for project_id in (foreign.pk, closed.pk, uuid4()):
        with pytest.raises(DomainError) as error:
            services.change_project(actor=world.olga, task_id=task.pk, project_id=project_id)
        assert error.value.code == "project_not_found"
        with pytest.raises(DomainError) as error:
            services.create_task(
                actor=world.olga,
                title="X",
                department_id=world.sales.pk,
                assignee_id=uid(world.anna),
                project_id=project_id,
            )
        assert error.value.code == "project_not_found"
    assert list(services.selectable_projects(world.olga)) == []


def test_project_of_another_department_becomes_selectable_with_an_own_participant(
    world: World,  # noqa: F811
) -> None:
    foreign = support_project(world)
    joined = projects.add_participant(
        actor=world.pavel,
        project_id=foreign.pk,
        user_id=uid(world.anna),
        department_id=world.sales.pk,
    )
    assert joined.invitation is not None
    assert list(services.selectable_projects(world.olga)) == []  # only invited so far
    projects.approve_invitation(actor=world.olga, invitation_id=joined.invitation.pk)

    assert list(services.selectable_projects(world.olga)) == [foreign]
    task = make_task(world)
    services.change_project(actor=world.olga, task_id=task.pk, project_id=foreign.pk)
    assert reload(task).project == foreign


def test_selectable_projects_are_for_those_who_place_tasks(world: World) -> None:  # noqa: F811
    sales_project(world)
    for actor in (world.anna, world.admin, world.zoya):
        with pytest.raises(PermissionDeniedError):
            services.selectable_projects(actor)


def test_a_task_in_a_project_is_still_invisible_to_its_participants(world: World) -> None:  # noqa: F811
    # D003, the point of the whole design.
    target = sales_project(world)
    projects.add_participant(
        actor=world.olga,
        project_id=target.pk,
        user_id=uid(world.boris),
        department_id=world.sales.pk,
    )
    invitation = projects.add_participant(
        actor=world.olga,
        project_id=target.pk,
        user_id=uid(world.vera),
        department_id=world.support.pk,
    ).invitation
    assert invitation is not None
    projects.approve_invitation(actor=world.pavel, invitation_id=invitation.pk)
    task = services.create_task(
        actor=world.olga,
        title="Секретная задача",
        department_id=world.sales.pk,
        assignee_id=uid(world.anna),
        project_id=target.pk,
    )

    for participant in (world.boris, world.vera, world.pavel):
        assert target in projects.visible_projects(participant)
        with pytest.raises(DomainError) as error:
            services.get_task(participant, task.pk)
        assert error.value.code == "task_not_found"
        assert list(services.board(participant, view="mine")) == []
    assert list(services.board(world.pavel, view="all")) == []
    # The assignee sees her task with its project although she takes no part in it.
    assert services.get_task(world.anna, task.pk).project == target


def test_archived_task_keeps_its_project_fixed(world: World) -> None:  # noqa: F811
    target = sales_project(world)
    task = make_task(world)
    services.archive_task(actor=world.olga, task_id=task.pk)
    with pytest.raises(DomainError) as error:
        services.change_project(actor=world.olga, task_id=task.pk, project_id=target.pk)
    assert error.value.code == "task_archived"


def test_api_project_on_card_and_in_edit(world: World) -> None:  # noqa: F811
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

    olga, anna = client(world.olga), client(world.anna)
    target = sales_project(world)

    options = call(olga, "get", "/api/v1/task-projects")
    assert options.json()["results"] == [{"id": str(target.pk), "name": "Запуск"}]
    assert call(anna, "get", "/api/v1/task-projects").status_code == 403

    created = call(
        olga,
        "post",
        "/api/v1/tasks",
        {
            "title": "Лендинг",
            "department_id": str(world.sales.pk),
            "assignee_id": str(uid(world.anna)),
            "project_id": str(target.pk),
        },
    )
    assert created.status_code == 201
    task = created.json()["task"]
    assert task["project"] == {"id": str(target.pk), "name": "Запуск"}
    assert task["actions"]["project"] is True
    base = f"/api/v1/tasks/{task['id']}"

    (card,) = anna.get("/api/v1/tasks").json()["results"]
    assert card["project"] == {"id": str(target.pk), "name": "Запуск"}
    assert call(anna, "get", base).json()["actions"]["project"] is False
    refused = call(anna, "patch", base, {"version": 1, "project_id": None})
    assert refused.status_code == 403

    cleared = call(olga, "patch", base, {"version": 1, "project_id": None})
    assert cleared.status_code == 200
    assert cleared.json()["project"] is None
    missing = call(olga, "patch", base, {"version": 2, "project_id": str(uuid4())})
    assert missing.status_code == 404
    assert "task.project_changed" in [
        e["action"] for e in call(olga, "get", base).json()["history"]
    ]
