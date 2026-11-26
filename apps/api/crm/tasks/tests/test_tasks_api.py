"""Tasks over HTTP: the same rules as the services, seen from outside."""

from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from crm.access import services as access
from crm.access.permissions import Scope
from crm.common.actors import Actor
from crm.conftest import STRONG_PASSWORD, Employee, EmployeeFactory
from crm.identity import auth
from crm.identity.models import LoginChallenge
from crm.organization import services as org
from crm.organization.models import Department
from crm.tasks.models import Task

pytestmark = pytest.mark.django_db

ORIGIN = "http://127.0.0.1:3000"


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
    client.post("/api/v1/auth/login/complete", headers={"Origin": ORIGIN})
    return client


def call(client: APIClient, method: str, path: str, data: object = None):  # type: ignore[no-untyped-def]
    return getattr(client, method)(path, data, format="json", headers={"Origin": ORIGIN})


@pytest.fixture
def sales(admin_actor: Actor) -> Department:
    return org.create_department(actor=admin_actor, name="Продажи")


@pytest.fixture
def team(
    admin_actor: Actor, make_employee: EmployeeFactory, sales: Department
) -> dict[str, Employee]:
    people = {name: make_employee(name) for name in ("olga", "anna", "boris", "vera")}
    for name in ("olga", "anna", "boris"):
        org.add_member(actor=admin_actor, department_id=sales.pk, user_id=people[name].user.pk)
    org.add_manager(actor=admin_actor, department_id=sales.pk, user_id=people["olga"].user.pk)
    # Vera may create tasks for any department without seeing them (for Q02).
    dispatcher = access.create_role(actor=admin_actor, key="dispatcher", name="Постановка задач")
    access.set_role_grants(
        actor=admin_actor, role=dispatcher, grants={"task.create": Scope.COMPANY}
    )
    access.assign_role(actor=admin_actor, user=people["vera"].user, role=dispatcher)
    return people


def new_task(client: APIClient, sales: Department, assignee: Employee, **extra: object):  # type: ignore[no-untyped-def]
    body = {
        "title": "Подготовить предложение",
        "department_id": str(sales.pk),
        "assignee_id": str(assignee.user.pk),
        **extra,
    }
    return call(client, "post", "/api/v1/tasks", body)


def statuses(client: APIClient) -> dict[str, dict[str, object]]:
    return {row["name"]: row for row in client.get("/api/v1/task-statuses").json()["results"]}


def test_tasks_api_needs_a_session() -> None:
    client = APIClient()

    for path in ("/api/v1/tasks", "/api/v1/task-statuses", f"/api/v1/tasks/{uuid4()}"):
        assert client.get(path).status_code == 401


def test_statuses_describe_the_board_and_its_moves(team: dict[str, Employee]) -> None:
    board = statuses(sign_in(team["anna"]))

    assert list(board) == ["Нужно сделать", "В работе", "Готово", "Отменено"]
    assert board["Готово"]["category"] == "completed"
    assert board["Готово"]["next_status_ids"] == []
    assert board["В работе"]["id"] in board["Нужно сделать"]["next_status_ids"]  # type: ignore[operator]


def test_creator_who_cannot_read_the_task_gets_only_a_receipt(
    team: dict[str, Employee], sales: Department
) -> None:
    # Q02: Vera (another department) creates a task for Anna.
    vera = sign_in(team["vera"])

    created = new_task(vera, sales, team["anna"])

    assert created.status_code == 201
    body = created.json()
    assert body["title"] == "Подготовить предложение"
    assert body["task"] is None
    assert vera.get(f"/api/v1/tasks/{body['id']}").status_code == 404
    assert vera.get("/api/v1/tasks?view=all").json()["results"] == []


def test_card_and_detail_carry_what_the_board_needs(
    team: dict[str, Employee], sales: Department
) -> None:
    olga, anna = sign_in(team["olga"]), sign_in(team["anna"])
    created = new_task(
        olga, sales, team["anna"], priority="high", due_at="2026-12-01T09:00:00Z"
    ).json()
    task_id = created["id"]
    assert created["task"]["id"] == task_id  # the manager may read what she created

    (card,) = anna.get("/api/v1/tasks").json()["results"]
    assert card == {
        "id": task_id,
        "title": "Подготовить предложение",
        "task_type": "task",
        "priority": "high",
        "status_id": statuses(anna)["Нужно сделать"]["id"],
        "due_at": "2026-12-01T09:00:00Z",
        "department": {"id": str(sales.pk), "name": "Продажи"},
        "project": None,
        "assignee": {"id": str(team["anna"].user.pk), "name": team["anna"].user.display_name},
        "checkpoints_done": 0,
        "checkpoints_total": 0,
        "is_completed": False,
        "is_archived": False,
        "is_deleted": False,
        "version": 1,
    }
    detail = anna.get(f"/api/v1/tasks/{task_id}").json()
    assert detail["author"]["name"] == team["olga"].user.display_name
    assert detail["actions"] == {
        "edit": True,
        "status": True,
        "deadline": True,
        "checkpoints_use": True,
        "checkpoints_manage": False,
        "attach": True,
        "attachment_delete": False,
        "comment": True,
        "comment_delete": False,
        "priority": False,
        "project": False,
        "reassign": False,
        "archive": False,
        "delete": False,
    }
    assert [entry["action"] for entry in detail["history"]] == ["task.created"]
    assert all(olga.get(f"/api/v1/tasks/{task_id}").json()["actions"].values())


def test_colleague_in_the_same_department_cannot_reach_the_task(
    team: dict[str, Employee], sales: Department
) -> None:
    task_id = new_task(sign_in(team["olga"]), sales, team["anna"]).json()["id"]
    boris = sign_in(team["boris"])
    base = f"/api/v1/tasks/{task_id}"

    assert boris.get(base).status_code == 404
    assert boris.get("/api/v1/tasks?view=all").json()["results"] == []
    assert call(boris, "patch", base, {"version": 1, "title": "Взлом"}).status_code == 404
    for action in ("archive", "reopen", "trash", "restore"):
        assert call(boris, "post", f"{base}/{action}").status_code == 404
    assert call(boris, "post", f"{base}/checkpoints", {"text": "x"}).status_code == 404
    assert Task.objects.get(pk=task_id).title == "Подготовить предложение"


def test_edit_form_is_saved_whole_or_not_at_all(
    team: dict[str, Employee], sales: Department
) -> None:
    task_id = new_task(sign_in(team["olga"]), sales, team["anna"]).json()["id"]
    anna = sign_in(team["anna"])
    base = f"/api/v1/tasks/{task_id}"

    # The assignee may edit the title but not the priority: nothing is saved.
    mixed = call(anna, "patch", base, {"version": 1, "title": "Новое", "priority": "urgent"})
    assert mixed.status_code == 403
    assert Task.objects.get(pk=task_id).title == "Подготовить предложение"

    ok = call(
        anna, "patch", base, {"version": 1, "title": "Новое", "due_at": "2026-12-05T10:00:00Z"}
    )
    assert ok.status_code == 200
    assert (ok.json()["title"], ok.json()["due_at"]) == ("Новое", "2026-12-05T10:00:00Z")

    stale = call(anna, "patch", base, {"version": 1, "title": "Старая вкладка"})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "task_changed"


def test_completing_moves_the_task_to_the_archive(
    team: dict[str, Employee], sales: Department
) -> None:
    anna = sign_in(team["anna"])
    task_id = new_task(sign_in(team["olga"]), sales, team["anna"]).json()["id"]
    board = statuses(anna)
    base = f"/api/v1/tasks/{task_id}"

    refused = call(anna, "post", f"{base}/transitions", {"status_id": str(uuid4())})
    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "transition_not_allowed"

    done = call(anna, "post", f"{base}/transitions", {"status_id": board["Готово"]["id"]})

    assert done.status_code == 200
    assert (done.json()["is_completed"], done.json()["is_archived"]) == (True, True)
    assert anna.get("/api/v1/tasks").json()["results"] == []
    assert [c["id"] for c in anna.get("/api/v1/tasks?view=archive").json()["results"]] == [task_id]
    # Seeing the archive gives no right to reopen (Q24).
    assert call(anna, "post", f"{base}/reopen").status_code == 403
    assert call(sign_in(team["olga"]), "post", f"{base}/reopen").json()["is_archived"] is False


def test_checkpoints_over_http_do_not_touch_the_status(
    team: dict[str, Employee], sales: Department
) -> None:
    anna = sign_in(team["anna"])
    task_id = new_task(sign_in(team["olga"]), sales, team["anna"]).json()["id"]
    base = f"/api/v1/tasks/{task_id}"

    added = call(anna, "post", f"{base}/checkpoints", {"text": "Собрать данные"}).json()
    (checkpoint,) = added["checkpoints"]
    ticked = call(anna, "patch", f"{base}/checkpoints/{checkpoint['id']}", {"is_done": True})

    assert ticked.json()["checkpoints"] == [
        {"id": checkpoint["id"], "text": "Собрать данные", "is_done": True}
    ]
    assert ticked.json()["status_id"] == added["status_id"]
    (card,) = anna.get("/api/v1/tasks").json()["results"]
    assert (card["checkpoints_done"], card["checkpoints_total"]) == (1, 1)
    assert call(anna, "delete", f"{base}/checkpoints/{checkpoint['id']}").status_code == 403


def test_trash_over_http(team: dict[str, Employee], sales: Department) -> None:
    olga, anna = sign_in(team["olga"]), sign_in(team["anna"])
    task_id = new_task(olga, sales, team["anna"]).json()["id"]
    base = f"/api/v1/tasks/{task_id}"

    assert call(anna, "post", f"{base}/trash").status_code == 403
    assert call(olga, "post", f"{base}/trash").json()["is_deleted"] is True
    assert anna.get(base).status_code == 404
    assert anna.get("/api/v1/tasks?view=trash").json()["results"] == []
    assert len(olga.get("/api/v1/tasks?view=trash").json()["results"]) == 1
    assert call(olga, "post", f"{base}/restore").json()["is_deleted"] is False
    assert anna.get(base).status_code == 200


def test_choices_for_a_new_task(team: dict[str, Employee], sales: Department) -> None:
    vera = sign_in(team["vera"])

    departments = vera.get("/api/v1/task-departments").json()["results"]
    assert departments == [{"id": str(sales.pk), "name": "Продажи"}]
    people = vera.get(f"/api/v1/task-assignees?department_id={sales.pk}").json()["results"]
    assert sorted(person["name"] for person in people) == sorted(
        team[name].user.display_name for name in ("olga", "anna", "boris")
    )
    assert set(people[0]) == {"id", "name"}  # names only
    assert vera.get("/api/v1/task-assignees?department_id=nope").status_code == 404
    assert vera.get("/api/v1/tasks?view=everything").status_code == 400


def test_invalid_task_is_refused_with_a_stable_code(
    team: dict[str, Employee], sales: Department
) -> None:
    anna = sign_in(team["olga"])

    outsider = new_task(anna, sales, team["vera"])
    assert (outsider.status_code, outsider.json()["error"]["code"]) == (
        400,
        "assignee_not_eligible",
    )
    blank = call(anna, "post", "/api/v1/tasks", {"title": "  ", "department_id": str(sales.pk)})
    assert blank.status_code == 400
    assert not Task.objects.exists()


def test_employee_cannot_create_a_task(team: dict[str, Employee], sales: Department) -> None:
    # D037: creating tasks is the manager's.
    anna = sign_in(team["anna"])

    assert new_task(anna, sales, team["anna"]).status_code == 403
    assert anna.get("/api/v1/task-departments").status_code == 403
    assert anna.get(f"/api/v1/task-assignees?department_id={sales.pk}").status_code == 403
    assert "task.create" not in anna.get("/api/v1/auth/me").json()["permissions"]
    assert not Task.objects.exists()
