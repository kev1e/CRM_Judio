"""Status administration (D005, Q04, Q05, Q09): only the holder of
`workflow.manage`, explicit replacement on retirement, nothing implicit."""

from uuid import UUID, uuid4

import pytest
from rest_framework.test import APIClient

from crm.access import services as access
from crm.access.permissions import ADMINISTRATOR_GRANTS, DEPARTMENT_MANAGER_GRANTS, Scope
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import Employee, EmployeeFactory
from crm.organization import services as org
from crm.organization.models import Department
from crm.tasks import services, workflow
from crm.tasks.models import StatusTransition, Task, TaskStatus
from crm.tasks.tests.test_tasks_api import call, sign_in

pytestmark = pytest.mark.django_db


def status(name: str) -> TaskStatus:
    return TaskStatus.objects.get(name=name)


@pytest.fixture
def sales(admin_actor: Actor) -> Department:
    return org.create_department(actor=admin_actor, name="Продажи")


@pytest.fixture
def olga(admin_actor: Actor, make_employee: EmployeeFactory, sales: Department) -> Employee:
    """Manager of Sales."""
    employee = make_employee("olga")
    org.add_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    org.add_manager(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    return employee


def make_task(olga: Employee, sales: Department, status_name: str | None = None) -> Task:
    actor = Actor.for_user(olga.user)
    task = services.create_task(
        actor=actor, title="Задача", department_id=sales.pk, assignee_id=olga.user.pk
    )
    if status_name:
        task = services.change_status(
            actor=actor, task_id=task.pk, status_id=status(status_name).pk
        )
    return task


def code(error: pytest.ExceptionInfo[DomainError]) -> str:
    return error.value.code


# --- Who may configure ------------------------------------------------------


def test_permission_belongs_to_the_administrator_only() -> None:
    assert ADMINISTRATOR_GRANTS["workflow.manage"] is Scope.COMPANY
    assert "workflow.manage" not in DEPARTMENT_MANAGER_GRANTS


def test_administrator_role_holds_the_grant_in_the_database(admin_actor: Actor) -> None:
    assert access.has_permission(admin_actor, "workflow.manage", at_least=Scope.COMPANY)


def test_manager_and_employee_cannot_configure(olga: Employee, employee: Employee) -> None:
    todo = status("Нужно сделать")
    for person in (olga, employee):
        actor = Actor.for_user(person.user)
        with pytest.raises(PermissionDeniedError):
            workflow.configuration(actor=actor)
        with pytest.raises(PermissionDeniedError):
            workflow.create_status(actor=actor, name="Проверка", category="active")
        with pytest.raises(PermissionDeniedError):
            workflow.rename_status(actor=actor, status_id=todo.pk, name="X")
        with pytest.raises(PermissionDeniedError):
            workflow.set_moves(actor=actor, status_id=todo.pk, next_status_ids=[])
        with pytest.raises(PermissionDeniedError):
            workflow.reorder(actor=actor, status_ids=[todo.pk])
        with pytest.raises(PermissionDeniedError):
            workflow.retire_status(actor=actor, status_id=todo.pk)
        with pytest.raises(PermissionDeniedError):
            workflow.restore_status(actor=actor, status_id=todo.pk)
    assert not AuditEvent.objects.filter(action__startswith="task_status.").exists()


def test_configuring_gives_no_sight_of_tasks(
    admin_actor: Actor, olga: Employee, sales: Department
) -> None:
    task = make_task(olga, sales)
    info = {i.status.name: i for i in workflow.configuration(actor=admin_actor)}
    assert info["Нужно сделать"].task_count == 1
    with pytest.raises(DomainError) as error:
        services.get_task(admin_actor, task.pk)
    assert code(error) == "task_not_found"


# --- Creating, renaming, ordering -------------------------------------------


def test_create_status_goes_last_and_is_audited(admin_actor: Actor) -> None:
    created = workflow.create_status(actor=admin_actor, name="  На   проверке ", category="active")
    assert created.name == "На проверке"
    assert created.position > status("Отменено").position
    event = AuditEvent.objects.get(action="task_status.created")
    assert event.entity_id == str(created.pk)
    assert event.metadata["category"] == "active"


@pytest.mark.parametrize(
    ("name", "category", "expected"),
    [
        ("", "active", "invalid_status_name"),
        ("x" * 81, "active", "invalid_status_name"),
        ("в работе", "active", "status_name_taken"),
        ("Проверка", "weird", "invalid_status_category"),
    ],
)
def test_create_status_refuses_bad_input(
    admin_actor: Actor, name: str, category: str, expected: str
) -> None:
    with pytest.raises(DomainError) as error:
        workflow.create_status(actor=admin_actor, name=name, category=category)
    assert code(error) == expected


def test_rename_keeps_identity_and_records_the_old_name(admin_actor: Actor) -> None:
    todo = status("Нужно сделать")
    workflow.rename_status(actor=admin_actor, status_id=todo.pk, name="Очередь")
    todo.refresh_from_db()
    assert todo.name == "Очередь"
    assert (
        AuditEvent.objects.get(action="task_status.renamed").metadata["before"] == "Нужно сделать"
    )
    with pytest.raises(DomainError) as error:
        workflow.rename_status(actor=admin_actor, status_id=todo.pk, name="Готово")
    assert code(error) == "status_name_taken"
    with pytest.raises(DomainError) as error:
        workflow.rename_status(actor=admin_actor, status_id=uuid4(), name="Нет")
    assert code(error) == "status_not_found"


def test_reorder_needs_every_active_status_once(admin_actor: Actor) -> None:
    ids = list(TaskStatus.objects.values_list("pk", flat=True))
    workflow.reorder(actor=admin_actor, status_ids=list(reversed(ids)))
    assert list(services.statuses().values_list("pk", flat=True)) == list(reversed(ids))
    for bad in (ids[:-1], [*ids, ids[0]], [*ids[:-1], uuid4()]):
        with pytest.raises(DomainError) as error:
            workflow.reorder(actor=admin_actor, status_ids=bad)
        assert code(error) == "invalid_order"


# --- Moves ------------------------------------------------------------------


def test_set_moves_replaces_the_list_and_is_enforced(
    admin_actor: Actor, olga: Employee, sales: Department
) -> None:
    todo, doing, done = status("Нужно сделать"), status("В работе"), status("Готово")
    workflow.set_moves(actor=admin_actor, status_id=todo.pk, next_status_ids=[doing.pk])
    assert set(
        StatusTransition.objects.filter(from_status=todo).values_list("to_status_id", flat=True)
    ) == {doing.pk}
    task = make_task(olga, sales)
    with pytest.raises(DomainError) as error:
        services.change_status(actor=Actor.for_user(olga.user), task_id=task.pk, status_id=done.pk)
    assert code(error) == "transition_not_allowed"
    event = AuditEvent.objects.get(action="task_status.moves_changed")
    assert str(done.pk) in event.metadata["removed"]


def test_set_moves_refuses_nonsense(admin_actor: Actor) -> None:
    todo, doing, done = status("Нужно сделать"), status("В работе"), status("Готово")
    cases: list[tuple[UUID, list[UUID]]] = [
        (todo.pk, [todo.pk]),
        (done.pk, [todo.pk]),
    ]
    for source, targets in cases:
        with pytest.raises(DomainError) as error:
            workflow.set_moves(actor=admin_actor, status_id=source, next_status_ids=targets)
        assert code(error) == "invalid_moves"
    with pytest.raises(DomainError) as error:
        workflow.set_moves(actor=admin_actor, status_id=todo.pk, next_status_ids=[uuid4()])
    assert code(error) == "status_not_found"
    extra = workflow.create_status(actor=admin_actor, name="Проверка", category="active")
    workflow.retire_status(actor=admin_actor, status_id=extra.pk)
    with pytest.raises(DomainError) as error:
        workflow.set_moves(actor=admin_actor, status_id=todo.pk, next_status_ids=[extra.pk])
    assert code(error) == "invalid_moves"
    with pytest.raises(DomainError) as error:
        workflow.set_moves(actor=admin_actor, status_id=extra.pk, next_status_ids=[doing.pk])
    assert code(error) == "status_retired"


# --- Retiring ---------------------------------------------------------------


def test_unused_status_retires_without_replacement(admin_actor: Actor) -> None:
    extra = workflow.create_status(actor=admin_actor, name="Проверка", category="active")
    assert workflow.retire_status(actor=admin_actor, status_id=extra.pk) == 0
    extra.refresh_from_db()
    assert not extra.is_active
    assert extra not in services.statuses()
    assert AuditEvent.objects.get(action="task_status.retired").metadata["moved_tasks"] == 0


def test_status_in_use_needs_an_explicit_replacement(
    admin_actor: Actor, olga: Employee, sales: Department
) -> None:
    task = make_task(olga, sales, "В работе")
    doing = status("В работе")
    with pytest.raises(DomainError) as error:
        workflow.retire_status(actor=admin_actor, status_id=doing.pk)
    assert code(error) == "replacement_required"
    task.refresh_from_db()
    assert task.status_id == doing.pk
    assert TaskStatus.objects.get(pk=doing.pk).is_active


def test_retiring_moves_tasks_to_the_chosen_status(
    admin_actor: Actor, olga: Employee, sales: Department
) -> None:
    doing, todo = status("В работе"), status("Нужно сделать")
    task = make_task(olga, sales, "В работе")
    untouched = make_task(olga, sales)
    version = task.row_version

    moved = workflow.retire_status(actor=admin_actor, status_id=doing.pk, replacement_id=todo.pk)

    assert moved == 1
    task.refresh_from_db()
    untouched_version = untouched.row_version
    untouched.refresh_from_db()
    assert task.status_id == todo.pk
    assert task.row_version == version + 1
    assert task.completed_at is None
    assert task.archived_at is None
    assert untouched.row_version == untouched_version
    remap = AuditEvent.objects.get(action="task.status_remapped")
    assert remap.entity_id == str(task.pk)
    assert remap.metadata == {
        "department_id": str(sales.pk),
        "before": str(doing.pk),
        "after": str(todo.pk),
    }
    retired = AuditEvent.objects.get(action="task_status.retired")
    assert retired.metadata["name"] == "В работе"
    assert retired.metadata["category"] == "active"
    assert retired.metadata["replacement_id"] == str(todo.pk)
    # History made before the retirement still names the old status.
    assert AuditEvent.objects.filter(
        action="task.status_changed", entity_id=str(task.pk), metadata__after=str(doing.pk)
    ).exists()


def test_completed_task_can_be_reopened_after_its_previous_status_was_retired(
    admin_actor: Actor, olga: Employee, sales: Department
) -> None:
    """Q05: reopening returns to the mapped status, never to a retired one."""
    doing, todo = status("В работе"), status("Нужно сделать")
    task = make_task(olga, sales, "В работе")
    actor = Actor.for_user(olga.user)
    services.change_status(actor=actor, task_id=task.pk, status_id=status("Готово").pk)

    workflow.retire_status(actor=admin_actor, status_id=doing.pk, replacement_id=todo.pk)

    reopened = services.reopen_task(actor=actor, task_id=task.pk)
    assert reopened.status_id == todo.pk
    assert reopened.completed_at is None


@pytest.mark.parametrize(
    ("retired", "replacement"),
    [("В работе", "Готово"), ("В работе", "Отменено"), ("Отменено", "В работе")],
)
def test_replacement_of_another_kind_is_refused(
    admin_actor: Actor, olga: Employee, sales: Department, retired: str, replacement: str
) -> None:
    task = make_task(olga, sales, "В работе")
    with pytest.raises(DomainError) as error:
        workflow.retire_status(
            actor=admin_actor,
            status_id=status(retired).pk,
            replacement_id=status(replacement).pk,
        )
    assert code(error) == "unsafe_replacement"
    task.refresh_from_db()
    assert task.completed_at is None
    assert status(retired).is_active


def test_completed_status_is_replaced_by_a_completed_one(
    admin_actor: Actor, olga: Employee, sales: Department
) -> None:
    task = make_task(olga, sales, "Готово")
    accepted = workflow.create_status(actor=admin_actor, name="Принято", category="completed")
    workflow.retire_status(
        actor=admin_actor, status_id=status("Готово").pk, replacement_id=accepted.pk
    )
    completed_at = task.completed_at
    task.refresh_from_db()
    assert task.status_id == accepted.pk
    assert task.completed_at == completed_at
    assert task.archived_at is not None


def test_replacement_must_be_another_active_status(admin_actor: Actor) -> None:
    doing = status("В работе")
    extra = workflow.create_status(actor=admin_actor, name="Проверка", category="active")
    workflow.retire_status(actor=admin_actor, status_id=extra.pk)
    for replacement in (doing.pk, extra.pk):
        with pytest.raises(DomainError) as error:
            workflow.retire_status(
                actor=admin_actor, status_id=doing.pk, replacement_id=replacement
            )
        assert code(error) == "invalid_replacement"
    with pytest.raises(DomainError) as error:
        workflow.retire_status(actor=admin_actor, status_id=extra.pk)
    assert code(error) == "status_retired"


def test_the_last_status_for_new_tasks_stays(admin_actor: Actor) -> None:
    todo = status("Нужно сделать")
    with pytest.raises(DomainError) as error:
        workflow.retire_status(
            actor=admin_actor, status_id=todo.pk, replacement_id=status("В работе").pk
        )
    assert code(error) == "last_new_status"
    queue = workflow.create_status(actor=admin_actor, name="Очередь", category="new")
    workflow.retire_status(actor=admin_actor, status_id=todo.pk, replacement_id=queue.pk)
    assert not status("Нужно сделать").is_active


def test_restore_returns_the_status_without_moving_tasks_back(
    admin_actor: Actor, olga: Employee, sales: Department
) -> None:
    doing, todo = status("В работе"), status("Нужно сделать")
    task = make_task(olga, sales, "В работе")
    workflow.retire_status(actor=admin_actor, status_id=doing.pk, replacement_id=todo.pk)

    workflow.restore_status(actor=admin_actor, status_id=doing.pk)

    doing.refresh_from_db()
    task.refresh_from_db()
    assert doing.is_active
    assert doing.position > status("Отменено").position
    assert task.status_id == todo.pk
    # Its old moves work again.
    services.change_status(actor=Actor.for_user(olga.user), task_id=task.pk, status_id=doing.pk)
    with pytest.raises(DomainError) as error:
        workflow.restore_status(actor=admin_actor, status_id=doing.pk)
    assert code(error) == "status_active"


# --- HTTP -------------------------------------------------------------------


@pytest.fixture
def admin_client(make_employee: EmployeeFactory, admin_actor: Actor) -> APIClient:
    from crm.access.models import Role

    boss = make_employee("boss")
    access.assign_role(
        actor=admin_actor, user=boss.user, role=Role.objects.get(key="administrator")
    )
    return sign_in(boss)


def test_api_requires_a_session() -> None:
    assert APIClient().get("/api/v1/workflow/statuses").status_code in (401, 403)


def test_api_is_closed_to_managers(olga: Employee) -> None:
    client = sign_in(olga)
    todo = status("Нужно сделать")
    assert call(client, "get", "/api/v1/workflow/statuses").status_code == 403
    requests = [
        ("post", "/api/v1/workflow/statuses", {"name": "Проверка", "category": "active"}),
        ("patch", f"/api/v1/workflow/statuses/{todo.pk}", {"name": "X"}),
        ("post", "/api/v1/workflow/order", {"status_ids": [str(todo.pk)]}),
        ("post", f"/api/v1/workflow/statuses/{todo.pk}/retire", {}),
        ("post", f"/api/v1/workflow/statuses/{todo.pk}/restore", None),
    ]
    for method, path, body in requests:
        assert call(client, method, path, body).status_code == 403, path
    assert status("Нужно сделать").name == "Нужно сделать"
    # The board's own list of statuses stays readable.
    assert call(client, "get", "/api/v1/task-statuses").status_code == 200


def test_api_round_trip(admin_client: APIClient, olga: Employee, sales: Department) -> None:
    make_task(olga, sales, "В работе")
    listing = call(admin_client, "get", "/api/v1/workflow/statuses")
    assert listing.status_code == 200
    assert listing["Cache-Control"] == "no-store"
    by_name = {s["name"]: s for s in listing.json()["results"]}
    assert by_name["В работе"]["task_count"] == 1
    assert by_name["В работе"]["is_active"] is True
    doing, todo = by_name["В работе"]["id"], by_name["Нужно сделать"]["id"]

    created = call(
        admin_client,
        "post",
        "/api/v1/workflow/statuses",
        {"name": "Проверка", "category": "active"},
    )
    assert created.status_code == 201
    review = next(s["id"] for s in created.json()["results"] if s["name"] == "Проверка")

    patched = call(
        admin_client,
        "patch",
        f"/api/v1/workflow/statuses/{review}",
        {"name": "На проверке", "next_status_ids": [doing]},
    )
    assert patched.status_code == 200
    row = next(s for s in patched.json()["results"] if s["id"] == review)
    assert row["name"] == "На проверке"
    assert row["next_status_ids"] == [doing]

    refused = call(admin_client, "post", f"/api/v1/workflow/statuses/{doing}/retire", {})
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "replacement_required"

    retired = call(
        admin_client,
        "post",
        f"/api/v1/workflow/statuses/{doing}/retire",
        {"replacement_id": todo},
    )
    assert retired.status_code == 200
    rows = {s["id"]: s for s in retired.json()["results"]}
    assert rows[doing]["is_active"] is False
    assert rows[doing]["task_count"] == 0
    assert rows[todo]["task_count"] == 1
    # A move into a retired status is not offered.
    assert rows[review]["next_status_ids"] == []

    restored = call(admin_client, "post", f"/api/v1/workflow/statuses/{doing}/restore")
    assert restored.status_code == 200

    order = [s["id"] for s in restored.json()["results"] if s["is_active"]]
    reordered = call(
        admin_client, "post", "/api/v1/workflow/order", {"status_ids": list(reversed(order))}
    )
    assert reordered.status_code == 200
    assert [s["id"] for s in reordered.json()["results"]] == list(reversed(order))

    missing = call(admin_client, "patch", f"/api/v1/workflow/statuses/{uuid4()}", {"name": "Нет"})
    assert missing.status_code == 404


# --- How the board shows a column (project on cards, division by project) ----


def test_display_defaults_and_the_existing_board(admin_actor: Actor) -> None:
    by_name = {info.status.name: info.status for info in workflow.configuration(actor=admin_actor)}

    # The columns "in work" stay divided, as the board showed them before the setting.
    assert by_name["В работе"].group_by_project is True
    assert by_name["Нужно сделать"].group_by_project is False
    assert all(item.show_project for item in by_name.values())
    created = workflow.create_status(actor=admin_actor, name="На проверке", category="active")
    assert (created.show_project, created.group_by_project) == (True, False)


def test_administrator_sets_the_display_of_a_status(admin_actor: Actor) -> None:
    created = workflow.create_status(
        actor=admin_actor, name="На проверке", category="active", group_by_project=True
    )
    assert created.group_by_project is True

    workflow.set_display(actor=admin_actor, status_id=created.pk, group_by_project=False)
    workflow.set_display(actor=admin_actor, status_id=created.pk, show_project=False)
    workflow.set_display(actor=admin_actor, status_id=created.pk, show_project=False)  # no change

    created.refresh_from_db()
    assert (created.show_project, created.group_by_project) == (False, False)
    events = AuditEvent.objects.filter(action="task_status.display_changed")
    assert [event.metadata["show_project"] for event in events.order_by("occurred_at")] == [
        True,
        False,
    ]


def test_division_needs_the_project_to_be_shown(admin_actor: Actor) -> None:
    with pytest.raises(DomainError) as error:
        workflow.create_status(
            actor=admin_actor,
            name="Странный",
            category="active",
            show_project=False,
            group_by_project=True,
        )
    assert code(error) == "invalid_status_display"

    divided = status("В работе")
    with pytest.raises(DomainError) as error:
        workflow.set_display(actor=admin_actor, status_id=divided.pk, show_project=False)
    assert code(error) == "invalid_status_display"
    # Both at once is fine.
    workflow.set_display(
        actor=admin_actor, status_id=divided.pk, show_project=False, group_by_project=False
    )


def test_only_the_administrator_changes_the_display(olga: Employee, employee: Employee) -> None:
    divided = status("В работе")

    for person in (olga, employee):
        with pytest.raises(PermissionDeniedError):
            workflow.set_display(
                actor=Actor.for_user(person.user), status_id=divided.pk, show_project=False
            )

    divided.refresh_from_db()
    assert divided.show_project is True


def test_api_carries_the_display_settings(admin_client: APIClient, olga: Employee) -> None:
    admin = admin_client

    created = call(
        admin,
        "post",
        "/api/v1/workflow/statuses",
        {"name": "На проверке", "category": "active", "group_by_project": True},
    )
    assert created.status_code == 201
    row = next(item for item in created.json()["results"] if item["name"] == "На проверке")
    assert (row["show_project"], row["group_by_project"]) == (True, True)

    refused = call(
        admin, "patch", f"/api/v1/workflow/statuses/{row['id']}", {"show_project": False}
    )
    assert (refused.status_code, refused.json()["error"]["code"]) == (400, "invalid_status_display")
    changed = call(
        admin,
        "patch",
        f"/api/v1/workflow/statuses/{row['id']}",
        {"show_project": False, "group_by_project": False},
    )
    assert changed.status_code == 200

    # The board of an ordinary user learns the settings with the statuses.
    board = sign_in(olga).get("/api/v1/task-statuses").json()["results"]
    seen = {item["name"]: (item["show_project"], item["group_by_project"]) for item in board}
    assert seen["На проверке"] == (False, False)
    assert seen["В работе"] == (True, True)
