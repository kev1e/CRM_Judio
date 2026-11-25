"""S3: tasks — who sees what, who may do what, and the lifecycle rules
(D005–D008, D015–D017, D019, Q02–Q09, Q19, Q24, Q29)."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from crm.access import services as access
from crm.access.models import Role
from crm.access.permissions import (
    BASELINE_GRANTS,
    DEPARTMENT_MANAGER_GRANTS,
    SUPERUSER_GRANTS,
    Scope,
)
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import EmployeeFactory
from crm.identity import users
from crm.identity.models import User
from crm.organization import services as org
from crm.organization.models import Department
from crm.tasks import policy, services
from crm.tasks.models import Checkpoint, StatusTransition, Task, TaskStatus

pytestmark = pytest.mark.django_db


@dataclass
class World:
    """Two departments. Sales: manager Olga, employees Anna and Boris.
    Support: manager Pavel, employee Vera. Zoya holds the superuser role.
    Vera also holds a custom role that lets her create tasks for any department
    without seeing them (used for Q02)."""

    admin: Actor
    sales: Department
    support: Department
    olga: Actor
    pavel: Actor
    anna: Actor
    boris: Actor
    vera: Actor
    zoya: Actor


@pytest.fixture
def world(admin_actor: Actor, make_employee: EmployeeFactory) -> World:
    sales = org.create_department(actor=admin_actor, name="Продажи")
    support = org.create_department(actor=admin_actor, name="Поддержка")
    people = {
        name: make_employee(name) for name in ("olga", "pavel", "anna", "boris", "vera", "zoya")
    }

    def place(name: str, department: Department, *, manager: bool = False) -> None:
        user_id = people[name].user.pk
        org.add_member(actor=admin_actor, department_id=department.pk, user_id=user_id)
        if manager:
            org.add_manager(actor=admin_actor, department_id=department.pk, user_id=user_id)

    place("olga", sales, manager=True)
    place("anna", sales)
    place("boris", sales)
    place("pavel", support, manager=True)
    place("vera", support)
    place("zoya", support)
    access.assign_role(
        actor=admin_actor, user=people["zoya"].user, role=Role.objects.get(key="superuser")
    )
    dispatcher = access.create_role(actor=admin_actor, key="dispatcher", name="Постановка задач")
    access.set_role_grants(
        actor=admin_actor, role=dispatcher, grants={"task.create": Scope.COMPANY}
    )
    access.assign_role(actor=admin_actor, user=people["vera"].user, role=dispatcher)
    actors = {name: Actor.for_user(employee.user) for name, employee in people.items()}
    return World(admin=admin_actor, sales=sales, support=support, **actors)


def uid(actor: Actor) -> UUID:
    assert actor.user is not None
    return actor.user.pk


def make_task(world: World, *, author: Actor | None = None, assignee: Actor | None = None) -> Task:
    """A Sales task assigned to Anna unless told otherwise."""
    return services.create_task(
        actor=author or world.olga,
        title="Подготовить коммерческое предложение",
        department_id=world.sales.pk,
        assignee_id=uid(assignee or world.anna),
    )


def status(name: str) -> TaskStatus:
    return TaskStatus.objects.get(name=name)


def reload(task: Task) -> Task:
    return Task.objects.get(pk=task.pk)


def actions_on(task: Task) -> list[str]:
    events = AuditEvent.objects.filter(entity_type="task", entity_id=str(task.pk))
    return list(events.order_by("occurred_at", "id").values_list("action", flat=True))


# --- Catalogue --------------------------------------------------------------


def test_built_in_roles_match_the_catalogue(world: World) -> None:
    assert access.effective_grants(world.anna.user) == BASELINE_GRANTS  # type: ignore[arg-type]
    assert access.effective_grants(world.olga.user) == DEPARTMENT_MANAGER_GRANTS  # type: ignore[arg-type]
    assert access.effective_grants(world.zoya.user) == {**BASELINE_GRANTS, **SUPERUSER_GRANTS}  # type: ignore[arg-type]
    # Q29: the superuser role reads everything and may do nothing more.
    assert SUPERUSER_GRANTS == {"task.read": Scope.COMPANY}
    # D003: being an administrator shows no tasks beyond one's own.
    assert access.scope_for(world.admin, "task.read") is Scope.OWN


def test_default_board_has_one_starting_and_one_completed_status(db: None) -> None:
    names = list(TaskStatus.objects.values_list("name", "category"))

    assert names == [
        ("Нужно сделать", "new"),
        ("В работе", "active"),
        ("Готово", "completed"),
        ("Отменено", "cancelled"),
    ]
    assert not StatusTransition.objects.filter(from_status__category="completed").exists()


# --- Who sees a task --------------------------------------------------------


def test_visibility_follows_assignee_department_manager_and_superuser(world: World) -> None:
    task = make_task(world)

    def sees(actor: Actor) -> bool:
        return policy.readable(actor).filter(pk=task.pk).exists()

    assert sees(world.anna)  # the assignee
    assert sees(world.olga)  # manager of the responsible department
    assert sees(world.zoya)  # superuser
    assert not sees(world.boris)  # same department, not the assignee
    assert not sees(world.pavel)  # manager of another department
    assert not sees(world.vera)
    assert not sees(world.admin)  # D003
    assert not sees(Actor.system("worker"))


def test_the_author_gets_no_access_from_authorship(world: World) -> None:
    # Q02: Vera asks Sales for something; she receives the task back but cannot open it.
    task = make_task(world, author=world.vera)

    assert task.author == world.vera.user
    assert not policy.allowed(world.vera, "task.read", task)
    with pytest.raises(DomainError) as error:
        services.get_task(world.vera, task.pk)
    assert error.value.code == "task_not_found"
    with pytest.raises(DomainError):
        services.update_content(actor=world.vera, task_id=task.pk, title="Другое")


def test_manager_of_one_department_does_not_see_another_even_through_a_shared_employee(
    world: World,
) -> None:
    # Boris also belongs to Support; a Sales task assigned to him stays invisible to Pavel.
    org.add_member(actor=world.admin, department_id=world.support.pk, user_id=uid(world.boris))
    task = make_task(world, assignee=world.boris)

    assert not policy.readable(world.pavel).filter(pk=task.pk).exists()
    assert policy.readable(world.olga).filter(pk=task.pk).exists()


def test_boards_show_only_what_the_viewer_may_see(world: World) -> None:
    annas = make_task(world)
    boriss = make_task(world, assignee=world.boris)
    olgas = make_task(world, assignee=world.olga)

    assert set(services.board(world.anna, view="mine")) == {annas}
    assert set(services.board(world.anna, view="all")) == {annas}
    assert set(services.board(world.olga, view="mine")) == {olgas}
    assert set(services.board(world.olga, view="all")) == {annas, boriss, olgas}
    assert set(services.board(world.zoya, view="all")) == {annas, boriss, olgas}
    assert set(services.board(world.pavel, view="all")) == set()
    assert list(services.board(Actor.system("worker"), view="all")) == []
    with pytest.raises(DomainError):
        services.board(world.anna, view="everything")


def test_rights_change_at_once_when_the_manager_is_removed(world: World) -> None:
    task = make_task(world, assignee=world.boris)
    assert services.get_task(world.olga, task.pk) == task

    org.remove_manager(actor=world.admin, department_id=world.sales.pk, user_id=uid(world.olga))

    with pytest.raises(DomainError):
        services.get_task(world.olga, task.pk)
    with pytest.raises(DomainError):
        services.change_priority(actor=world.olga, task_id=task.pk, priority="high")


# --- Creating ---------------------------------------------------------------


def test_created_task_is_assigned_at_once(world: World) -> None:
    due = timezone.now() + timedelta(days=3)

    task = services.create_task(
        actor=world.vera,
        title="  Счёт   для клиента ",
        description=" Нужен до пятницы ",
        department_id=world.sales.pk,
        assignee_id=uid(world.anna),
        priority="high",
        due_at=due,
        task_type="request",
    )

    assert task.title == "Счёт для клиента"
    assert task.description == "Нужен до пятницы"
    assert (task.status.category, task.priority, task.task_type) == ("new", "high", "request")
    assert task.assignee == world.anna.user
    assert task.responsible_department == world.sales
    assert (task.due_at, task.original_due_at) == (due, due)
    assert set(services.board(world.anna, view="mine")) == {task}
    assert actions_on(task) == ["task.created"]
    # Titles and descriptions stay out of the audit log.
    assert "Счёт" not in str(list(AuditEvent.objects.values_list("metadata", flat=True)))


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"title": "   "}, "invalid_title"),
        ({"title": "x" * 201}, "invalid_title"),
        ({"priority": "critical"}, "invalid_priority"),
        ({"task_type": "bug"}, "invalid_task_type"),
        ({"department_id": uuid4()}, "department_not_found"),
        ({"assignee_id": uuid4()}, "assignee_not_eligible"),
    ],
)
def test_invalid_tasks_are_refused(world: World, overrides: dict[str, object], code: str) -> None:
    params: dict[str, object] = {
        "actor": world.vera,
        "title": "Задача",
        "department_id": world.sales.pk,
        "assignee_id": uid(world.boris),
    }
    params.update(overrides)

    with pytest.raises(DomainError) as error:
        services.create_task(**params)  # type: ignore[arg-type]

    assert error.value.code == code
    assert not Task.objects.exists()


def test_assignee_must_be_an_active_member_of_the_responsible_department(world: World) -> None:
    for outsider in (world.vera, world.admin):
        with pytest.raises(DomainError) as error:
            make_task(world, assignee=outsider)
        assert error.value.code == "assignee_not_eligible"

    org.set_department_active(actor=world.admin, department_id=world.support.pk, active=True)
    assert world.boris.user is not None
    User.objects.filter(pk=world.boris.user.pk).update(
        is_active=False, deactivated_at=timezone.now()
    )
    with pytest.raises(DomainError):
        make_task(world, assignee=world.boris)


# --- D037: who creates tasks and for whom -----------------------------------


def test_only_a_manager_creates_tasks(world: World) -> None:
    assert "task.create" not in BASELINE_GRANTS
    assert DEPARTMENT_MANAGER_GRANTS["task.create"] is Scope.MANAGED_DEPARTMENTS
    # An employee cannot create a task, not even for themselves; nor can the
    # administrator or the read-only superuser.
    for actor in (world.anna, world.admin, world.zoya):
        with pytest.raises(PermissionDeniedError):
            make_task(world, author=actor)
        with pytest.raises(PermissionDeniedError):
            services.assignable_departments(actor)
        with pytest.raises(PermissionDeniedError):
            services.eligible_assignees(actor, world.sales.pk)
    assert not Task.objects.exists()


def test_manager_creates_tasks_only_for_a_managed_department(world: World) -> None:
    assert list(services.assignable_departments(world.olga)) == [world.sales]
    with pytest.raises(PermissionDeniedError):
        services.create_task(
            actor=world.olga, title="X", department_id=world.support.pk, assignee_id=uid(world.vera)
        )
    with pytest.raises(PermissionDeniedError):
        services.eligible_assignees(world.olga, world.support.pk)
    assert not Task.objects.exists()


def test_assignee_is_an_employee_or_a_manager_of_the_department(world: World) -> None:
    # Pavel manages Support without belonging to it.
    assert world.pavel.user is not None
    org.remove_member(
        actor=world.admin, department_id=world.support.pk, user_id=world.pavel.user.pk
    )
    logins = [u.crm_login for u in services.eligible_assignees(world.pavel, world.support.pk)]
    assert sorted(logins) == ["pavel", "vera", "zoya"]

    to_self = services.create_task(
        actor=world.pavel,
        title="Себе",
        department_id=world.support.pk,
        assignee_id=uid(world.pavel),
    )
    to_employee = services.create_task(
        actor=world.pavel, title="Вере", department_id=world.support.pk, assignee_id=uid(world.vera)
    )
    assert to_self.assignee == world.pavel.user
    assert to_employee.assignee == world.vera.user
    # A manager of another department is not eligible.
    with pytest.raises(DomainError) as error:
        services.create_task(
            actor=world.pavel,
            title="X",
            department_id=world.support.pk,
            assignee_id=uid(world.olga),
        )
    assert error.value.code == "assignee_not_eligible"


def test_employee_who_lost_the_manager_role_cannot_create_any_more(world: World) -> None:
    make_task(world, author=world.olga)
    org.add_manager(
        actor=world.admin, department_id=world.sales.pk, user_id=uid(world.boris), designated=True
    )
    org.remove_manager(actor=world.admin, department_id=world.sales.pk, user_id=uid(world.olga))
    with pytest.raises(PermissionDeniedError):
        make_task(world, author=world.olga)


def test_non_employees_cannot_create_tasks(world: World) -> None:
    for actor in (Actor.system("worker"), Actor.cli("os:root")):
        with pytest.raises(PermissionDeniedError):
            make_task(world, author=actor)


def test_task_cannot_be_addressed_to_a_closed_department(world: World) -> None:
    empty = org.create_department(actor=world.admin, name="Закрытый")
    org.set_department_active(actor=world.admin, department_id=empty.pk, active=False)

    with pytest.raises(DomainError) as error:
        services.create_task(
            actor=world.vera, title="X", department_id=empty.pk, assignee_id=uid(world.anna)
        )

    assert error.value.code == "department_not_found"
    assert empty not in services.assignable_departments(world.vera)


def test_eligible_assignees_are_the_active_members(world: World) -> None:
    names = [user.crm_login for user in services.eligible_assignees(world.vera, world.sales.pk)]

    assert sorted(names) == ["anna", "boris", "olga"]


# --- Field permissions (Q19) ------------------------------------------------

Operation = Callable[[Actor, Task, World], object]

OPERATIONS: dict[str, Operation] = {
    "content": lambda a, t, w: services.update_content(actor=a, task_id=t.pk, title="Новое"),
    "status": lambda a, t, w: services.change_status(
        actor=a, task_id=t.pk, status_id=status("В работе").pk
    ),
    "deadline": lambda a, t, w: services.change_deadline(
        actor=a, task_id=t.pk, due_at=timezone.now() + timedelta(days=1)
    ),
    "checkpoint": lambda a, t, w: services.add_checkpoint(actor=a, task_id=t.pk, label="Шаг"),
    "priority": lambda a, t, w: services.change_priority(actor=a, task_id=t.pk, priority="urgent"),
    "reassign": lambda a, t, w: services.reassign(actor=a, task_id=t.pk, assignee_id=uid(w.boris)),
    "archive": lambda a, t, w: services.archive_task(actor=a, task_id=t.pk),
    "trash": lambda a, t, w: services.trash_task(actor=a, task_id=t.pk),
}
ASSIGNEE_MAY = {"content", "status", "deadline", "checkpoint"}


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_what_the_assignee_may_do(world: World, operation: str) -> None:
    task = make_task(world)

    if operation in ASSIGNEE_MAY:
        OPERATIONS[operation](world.anna, task, world)
        assert reload(task).row_version == 2
    else:
        # Priority, assignee, manual archive and deletion are the manager's.
        with pytest.raises(PermissionDeniedError):
            OPERATIONS[operation](world.anna, task, world)
        assert reload(task).row_version == 1


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_the_manager_of_the_department_may_do_everything(world: World, operation: str) -> None:
    task = make_task(world)

    OPERATIONS[operation](world.olga, task, world)

    assert reload(task).row_version == 2


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
@pytest.mark.parametrize("who", ["boris", "pavel", "vera", "admin"])
def test_people_who_cannot_see_the_task_can_do_nothing(
    world: World, operation: str, who: str
) -> None:
    task = make_task(world)

    # For them the task does not exist: the answer does not reveal that it does.
    with pytest.raises(DomainError) as error:
        OPERATIONS[operation](getattr(world, who), task, world)

    assert error.value.code == "task_not_found"
    assert reload(task).row_version == 1
    assert actions_on(task) == ["task.created"]


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_the_superuser_sees_everything_and_changes_nothing(world: World, operation: str) -> None:
    # Q29: reading is company-wide, every action needs its own grant.
    task = make_task(world)
    assert services.get_task(world.zoya, task.pk) == task

    with pytest.raises(PermissionDeniedError):
        OPERATIONS[operation](world.zoya, task, world)

    assert reload(task).row_version == 1


def test_superuser_acts_only_with_a_separately_granted_right(world: World) -> None:
    task = make_task(world)
    role = access.create_role(actor=world.admin, key="task_closer", name="Закрытие задач")
    access.set_role_grants(actor=world.admin, role=role, grants={"task.status": Scope.COMPANY})
    assert world.zoya.user is not None
    access.assign_role(actor=world.admin, user=world.zoya.user, role=role)

    services.change_status(actor=world.zoya, task_id=task.pk, status_id=status("В работе").pk)

    with pytest.raises(PermissionDeniedError):
        services.change_priority(actor=world.zoya, task_id=task.pk, priority="high")


def test_action_right_without_read_access_is_useless(world: World) -> None:
    # A company-wide action grant does not open tasks the holder cannot read:
    # reading stays OWN, so for the holder the task does not exist.
    task = make_task(world)
    role = access.create_role(actor=world.admin, key="prioritizer", name="Приоритеты")
    access.set_role_grants(actor=world.admin, role=role, grants={"task.priority": Scope.COMPANY})
    assert world.vera.user is not None
    access.assign_role(actor=world.admin, user=world.vera.user, role=role)

    with pytest.raises(DomainError) as error:
        services.change_priority(actor=world.vera, task_id=task.pk, priority="high")

    assert error.value.code == "task_not_found"


def test_interface_hints_match_what_the_services_allow(world: World) -> None:
    task = make_task(world)

    assert policy.actions(world.anna, task) == {
        "task.update": True,
        "task.status": True,
        "task.deadline": True,
        "task.checkpoints.use": True,
        "task.checkpoints.manage": False,
        "task.comment": True,
        "task.comment.delete": False,
        "task.priority": False,
        "task.reassign": False,
        "task.archive": False,
        "task.delete": False,
    }
    assert all(policy.actions(world.olga, task).values())
    assert not any(policy.actions(world.zoya, task).values())


# --- Editing ----------------------------------------------------------------


def test_deadline_change_keeps_both_values_and_the_original_deadline(world: World) -> None:
    first = timezone.now() + timedelta(days=2)
    task = services.create_task(
        actor=world.olga,
        title="Задача",
        department_id=world.sales.pk,
        assignee_id=uid(world.anna),
        due_at=first,
    )
    later = first + timedelta(days=5)

    services.change_deadline(actor=world.anna, task_id=task.pk, due_at=later)

    task = reload(task)
    assert (task.due_at, task.original_due_at) == (later, first)  # Q17
    event = AuditEvent.objects.get(action="task.deadline_changed")
    assert event.metadata["before"] == first.isoformat()
    assert event.metadata["after"] == later.isoformat()
    assert event.actor == world.anna.user


def test_first_deadline_set_later_becomes_the_original_one(world: World) -> None:
    task = make_task(world)
    due = timezone.now() + timedelta(days=1)

    services.change_deadline(actor=world.anna, task_id=task.pk, due_at=due)
    services.change_deadline(actor=world.anna, task_id=task.pk, due_at=None)

    task = reload(task)
    assert (task.due_at, task.original_due_at) == (None, due)


def test_reassigning_starts_a_new_assignment_and_moves_visibility(world: World) -> None:
    task = make_task(world)
    assigned_first = task.assigned_at

    services.reassign(actor=world.olga, task_id=task.pk, assignee_id=uid(world.boris))

    task = reload(task)
    assert task.assignee == world.boris.user
    assert task.assigned_at > assigned_first  # Q18
    assert not policy.readable(world.anna).filter(pk=task.pk).exists()
    assert policy.readable(world.boris).filter(pk=task.pk).exists()
    with pytest.raises(DomainError) as error:
        services.reassign(actor=world.olga, task_id=task.pk, assignee_id=uid(world.vera))
    assert error.value.code == "assignee_not_eligible"


def test_stale_edit_is_refused(world: World) -> None:
    task = make_task(world)
    services.update_content(actor=world.olga, task_id=task.pk, title="Правка руководителя")

    with pytest.raises(services.StaleTaskError):
        services.update_content(
            actor=world.anna, task_id=task.pk, title="Правка исполнителя", expected_version=1
        )

    assert reload(task).title == "Правка руководителя"
    services.update_content(
        actor=world.anna, task_id=task.pk, title="Правка исполнителя", expected_version=2
    )


def test_unchanged_values_write_nothing(world: World) -> None:
    task = make_task(world)

    services.update_content(actor=world.anna, task_id=task.pk, title=task.title)
    services.change_priority(actor=world.olga, task_id=task.pk, priority=task.priority)
    services.change_status(actor=world.anna, task_id=task.pk, status_id=task.status_id)

    assert reload(task).row_version == 1
    assert actions_on(task) == ["task.created"]


# --- Statuses, completion and the archive -----------------------------------


def test_only_configured_moves_are_allowed(world: World) -> None:
    task = make_task(world)
    cancelled, todo = status("Отменено"), status("Нужно сделать")
    services.change_status(actor=world.anna, task_id=task.pk, status_id=cancelled.pk)

    # "Отменено" -> "В работе" is not configured.
    with pytest.raises(DomainError) as error:
        services.change_status(actor=world.anna, task_id=task.pk, status_id=status("В работе").pk)
    assert error.value.code == "transition_not_allowed"
    with pytest.raises(DomainError):
        services.change_status(actor=world.anna, task_id=task.pk, status_id=uuid4())

    services.change_status(actor=world.anna, task_id=task.pk, status_id=todo.pk)
    assert reload(task).status == todo


def test_completion_archives_the_task_in_the_same_step(world: World) -> None:
    task = make_task(world)
    services.change_status(actor=world.anna, task_id=task.pk, status_id=status("В работе").pk)

    done = services.change_status(actor=world.anna, task_id=task.pk, status_id=status("Готово").pk)

    assert done.completed_at is not None
    assert done.archived_at == done.completed_at  # D016
    assert done.status.name == "Готово"  # the archive keeps the completed status
    assert done.status_before_completion == status("В работе")
    assert list(services.board(world.anna, view="mine")) == []
    assert list(services.board(world.olga, view="all")) == []
    assert set(services.board(world.anna, view="archive")) == {task}  # Q24
    assert actions_on(task)[-1] == "task.completed"


def test_cancelled_is_not_completed_and_is_not_archived(world: World) -> None:
    task = make_task(world)

    cancelled = services.change_status(
        actor=world.anna, task_id=task.pk, status_id=status("Отменено").pk
    )

    assert cancelled.completed_at is None  # Q04
    assert cancelled.archived_at is None
    assert set(services.board(world.anna, view="mine")) == {task}


def test_database_refuses_a_completed_task_that_is_not_archived(world: World) -> None:
    task = make_task(world)

    with pytest.raises(IntegrityError), transaction.atomic():
        Task.objects.filter(pk=task.pk).update(completed_at=timezone.now())


def test_checkpoints_never_change_the_status(world: World) -> None:
    task = make_task(world)
    first = services.add_checkpoint(actor=world.anna, task_id=task.pk, label="  Собрать   данные ")
    second = services.add_checkpoint(actor=world.anna, task_id=task.pk, label="Отправить")

    for checkpoint in (first, second):
        services.set_checkpoint_done(
            actor=world.anna, task_id=task.pk, checkpoint_id=checkpoint.pk, done=True
        )

    task = reload(task)
    assert task.status.category == "new"  # D015: all ticked, nothing moved
    assert task.completed_at is None
    assert task.archived_at is None
    assert [(c.label, c.is_done) for c in task.checkpoints.all()] == [
        ("Собрать данные", True),
        ("Отправить", True),
    ]
    done = Checkpoint.objects.get(pk=first.pk)
    assert done.done_by == world.anna.user

    services.set_checkpoint_done(
        actor=world.anna, task_id=task.pk, checkpoint_id=first.pk, done=False
    )
    undone = Checkpoint.objects.get(pk=first.pk)
    assert (undone.is_done, undone.done_by, undone.done_at) == (False, None, None)


def test_assignee_adds_and_ticks_checkpoints_but_only_a_manager_removes_them(
    world: World,
) -> None:
    task = make_task(world)
    checkpoint = services.add_checkpoint(actor=world.anna, task_id=task.pk, label="Шаг")

    with pytest.raises(PermissionDeniedError):
        services.remove_checkpoint(actor=world.anna, task_id=task.pk, checkpoint_id=checkpoint.pk)
    services.remove_checkpoint(actor=world.olga, task_id=task.pk, checkpoint_id=checkpoint.pk)

    assert not task.checkpoints.exists()
    with pytest.raises(DomainError):
        services.add_checkpoint(actor=world.anna, task_id=task.pk, label="   ")
    other = make_task(world)
    foreign = services.add_checkpoint(actor=world.anna, task_id=other.pk, label="Чужой")
    with pytest.raises(DomainError) as error:
        services.set_checkpoint_done(
            actor=world.anna, task_id=task.pk, checkpoint_id=foreign.pk, done=True
        )
    assert error.value.code == "checkpoint_not_found"


def test_manual_archive_does_not_complete_the_task(world: World) -> None:
    task = make_task(world)

    archived = services.archive_task(actor=world.olga, task_id=task.pk)

    assert archived.archived_at is not None
    assert archived.completed_at is None  # Q05
    assert archived.status.category == "new"
    assert set(services.board(world.anna, view="archive")) == {task}
    assert list(services.board(world.anna, view="mine")) == []


def test_archived_task_is_read_only_until_reopened(world: World) -> None:
    task = make_task(world)
    services.archive_task(actor=world.olga, task_id=task.pk)

    for operation in (
        "content",
        "status",
        "deadline",
        "checkpoint",
        "priority",
        "reassign",
        "archive",
    ):
        with pytest.raises(DomainError) as error:
            OPERATIONS[operation](world.olga, task, world)
        assert error.value.code == "task_archived"

    assert services.get_task(world.anna, task.pk) == task  # still readable


def test_reopening_returns_a_completed_task_to_its_previous_status(world: World) -> None:
    task = make_task(world)
    services.change_status(actor=world.anna, task_id=task.pk, status_id=status("В работе").pk)
    services.change_status(actor=world.anna, task_id=task.pk, status_id=status("Готово").pk)

    # Seeing the archive does not allow reopening (Q24).
    with pytest.raises(PermissionDeniedError):
        services.reopen_task(actor=world.anna, task_id=task.pk)
    reopened = services.reopen_task(actor=world.olga, task_id=task.pk)

    assert reopened.status == status("В работе")
    assert reopened.completed_at is None
    assert reopened.archived_at is None
    assert reopened.status_before_completion is None
    assert set(services.board(world.anna, view="mine")) == {task}
    assert actions_on(task)[-1] == "task.reopened"


def test_reopening_a_manually_archived_task_only_unarchives_it(world: World) -> None:
    task = make_task(world)
    services.archive_task(actor=world.olga, task_id=task.pk)

    reopened = services.reopen_task(actor=world.olga, task_id=task.pk)

    assert reopened.archived_at is None
    assert reopened.status.category == "new"
    with pytest.raises(DomainError) as error:
        services.reopen_task(actor=world.olga, task_id=task.pk)
    assert error.value.code == "task_not_archived"


def test_reopening_is_refused_when_the_previous_status_is_gone(world: World) -> None:
    # Q07: a replacement status is never picked automatically.
    task = make_task(world)
    services.change_status(actor=world.anna, task_id=task.pk, status_id=status("Готово").pk)
    TaskStatus.objects.filter(name="Нужно сделать").update(is_active=False)

    with pytest.raises(DomainError) as error:
        services.reopen_task(actor=world.olga, task_id=task.pk)

    assert error.value.code == "previous_status_unavailable"
    assert reload(task).archived_at is not None


# --- Trash (Q06) ------------------------------------------------------------


def test_trash_hides_the_task_and_restore_brings_it_back_unchanged(world: World) -> None:
    task = make_task(world)

    trashed = services.trash_task(actor=world.olga, task_id=task.pk)

    assert trashed.deleted_by == world.olga.user
    assert list(services.board(world.anna, view="mine")) == []
    assert list(services.board(world.anna, view="archive")) == []
    assert list(services.board(world.anna, view="trash")) == []  # not the assignee's to see
    assert set(services.board(world.olga, view="trash")) == {task}
    with pytest.raises(DomainError) as hidden:
        services.get_task(world.anna, task.pk)
    assert hidden.value.code == "task_not_found"
    with pytest.raises(DomainError) as locked:
        services.update_content(actor=world.olga, task_id=task.pk, title="X")
    assert locked.value.code == "task_deleted"
    assert Task.objects.filter(pk=task.pk).exists()  # nothing is removed

    restored = services.restore_task(actor=world.olga, task_id=task.pk)

    assert (restored.deleted_at, restored.deleted_by) == (None, None)
    assert set(services.board(world.anna, view="mine")) == {task}
    assert actions_on(task)[-2:] == ["task.trashed", "task.restored"]


def test_trash_of_another_department_is_invisible(world: World) -> None:
    task = make_task(world)
    services.trash_task(actor=world.olga, task_id=task.pk)

    assert list(services.board(world.pavel, view="trash")) == []
    assert list(services.board(world.zoya, view="trash")) == []  # read-only superuser
    with pytest.raises(DomainError):
        services.restore_task(actor=world.pavel, task_id=task.pk)


def test_archive_and_trash_are_different_places(world: World) -> None:
    task = make_task(world)
    services.archive_task(actor=world.olga, task_id=task.pk)
    services.trash_task(actor=world.olga, task_id=task.pk)

    assert list(services.board(world.olga, view="archive")) == []
    services.restore_task(actor=world.olga, task_id=task.pk)
    assert set(services.board(world.olga, view="archive")) == {task}  # still archived


# --- Deactivation hand-over (D019, Q08) -------------------------------------


def test_open_tasks_go_to_the_designated_manager_on_deactivation(world: World) -> None:
    open_task = make_task(world)
    done_task = make_task(world)
    services.change_status(actor=world.anna, task_id=done_task.pk, status_id=status("Готово").pk)
    cancelled_task = make_task(world)
    services.change_status(
        actor=world.anna, task_id=cancelled_task.pk, status_id=status("Отменено").pk
    )
    assert world.anna.user is not None

    users.deactivate_user(actor=world.admin, user=world.anna.user)

    assert reload(open_task).assignee == world.olga.user
    # Finished and cancelled work stays with the person who did it.
    assert reload(done_task).assignee == world.anna.user
    assert reload(cancelled_task).assignee == world.anna.user
    event = AuditEvent.objects.filter(action="task.reassigned").latest("occurred_at")
    assert event.metadata["reason"] == "deactivation"
    assert AuditEvent.objects.get(action="user.deactivated").metadata == {"tasks_handed_over": 1}


def test_deactivation_is_refused_when_nobody_can_take_the_tasks(world: World) -> None:
    # The manager herself has open tasks and is the only manager of her department.
    task = make_task(world, assignee=world.olga)
    assert world.olga.user is not None

    with pytest.raises(DomainError) as error:
        users.deactivate_user(actor=world.admin, user=world.olga.user)

    assert error.value.code == "handover_target_missing"
    world.olga.user.refresh_from_db()
    assert world.olga.user.is_active
    assert reload(task).assignee == world.olga.user


def test_employee_without_open_tasks_is_deactivated_without_a_manager(world: World) -> None:
    org.remove_manager(actor=world.admin, department_id=world.support.pk, user_id=uid(world.pavel))
    assert world.vera.user is not None

    assert users.deactivate_user(actor=world.admin, user=world.vera.user) is True
