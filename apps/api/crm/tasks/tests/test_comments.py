"""Task comments (D006, Q19, Q24): who may comment, own-comment editing with
kept revisions, and no way around the task's access rules."""

from uuid import uuid4

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from crm.access import services as access
from crm.access.models import Role
from crm.access.permissions import BASELINE_GRANTS, DEPARTMENT_MANAGER_GRANTS, Scope
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import Employee
from crm.organization.models import Department
from crm.tasks import policy, services
from crm.tasks.models import Comment, CommentRevision
from crm.tasks.tests.test_tasks import World, make_task, reload, uid, world  # noqa: F401
from crm.tasks.tests.test_tasks_api import call, new_task, sales, sign_in, team  # noqa: F401

pytestmark = pytest.mark.django_db

SECRET_TEXT = "Клиент просит скидку 15 процентов"


def test_grants() -> None:
    assert BASELINE_GRANTS["task.comment"] is Scope.OWN
    assert DEPARTMENT_MANAGER_GRANTS["task.comment"] is Scope.MANAGED_DEPARTMENTS


def test_manager_role_holds_the_grant_in_the_database() -> None:
    role = Role.objects.get(key="department_manager")
    assert role.grants.get(permission_code="task.comment").scope == "managed_departments"


# --- Adding -----------------------------------------------------------------


def test_assignee_and_manager_comment(world: World) -> None:  # noqa: F811
    task = make_task(world)

    first = services.add_comment(actor=world.anna, task_id=task.pk, body=f"  {SECRET_TEXT}\r\n ")
    second = services.add_comment(actor=world.olga, task_id=task.pk, body="Согласовано")

    assert first.body == SECRET_TEXT
    assert first.author_id == uid(world.anna)
    assert (first.revision, first.edited_at) == (1, None)
    assert list(services.comments(world.anna, task)) == [first, second]
    # A comment does not make somebody's open edit form stale.
    assert reload(task).row_version == 1


def test_comment_text_never_reaches_the_audit_log(world: World) -> None:  # noqa: F811
    task = make_task(world)
    comment = services.add_comment(actor=world.anna, task_id=task.pk, body=SECRET_TEXT)
    services.edit_comment(
        actor=world.anna, task_id=task.pk, comment_id=comment.pk, body="Другой текст"
    )

    added = AuditEvent.objects.get(action="task.comment_added")
    edited = AuditEvent.objects.get(action="task.comment_edited")
    assert added.entity_id == str(task.pk)
    assert added.metadata == {
        "department_id": str(world.sales.pk),
        "comment_id": str(comment.pk),
    }
    assert edited.metadata["revision"] == 2
    for event in AuditEvent.objects.all():
        assert SECRET_TEXT not in str(event.metadata)
        assert "Другой текст" not in str(event.metadata)


@pytest.mark.parametrize("who", ["boris", "pavel", "vera"])
def test_outsiders_neither_comment_nor_read(world: World, who: str) -> None:  # noqa: F811
    task = make_task(world)
    services.add_comment(actor=world.anna, task_id=task.pk, body=SECRET_TEXT)
    actor: Actor = getattr(world, who)

    with pytest.raises(DomainError) as error:
        services.add_comment(actor=actor, task_id=task.pk, body="Можно?")

    assert error.value.code == "task_not_found"
    assert list(services.comments(actor, task)) == []
    assert Comment.objects.count() == 1


def test_author_of_the_task_without_access_cannot_comment(world: World) -> None:  # noqa: F811
    # Q02: authorship gives nothing. Vera (Support) creates a task for Sales.
    task = make_task(world, author=world.vera)
    with pytest.raises(DomainError) as error:
        services.add_comment(actor=world.vera, task_id=task.pk, body="Как дела?")
    assert error.value.code == "task_not_found"


def test_superuser_reads_comments_but_does_not_write(world: World) -> None:  # noqa: F811
    # Q29: company-wide reading; commenting needs its own grant.
    task = make_task(world)
    comment = services.add_comment(actor=world.anna, task_id=task.pk, body=SECRET_TEXT)

    assert list(services.comments(world.zoya, task)) == [comment]
    assert policy.actions(world.zoya, task)["task.comment"] is False
    with pytest.raises(PermissionDeniedError):
        services.add_comment(actor=world.zoya, task_id=task.pk, body="Вижу")

    role = access.create_role(actor=world.admin, key="commenter", name="Комментарии")
    access.set_role_grants(actor=world.admin, role=role, grants={"task.comment": Scope.COMPANY})
    assert world.zoya.user is not None
    access.assign_role(actor=world.admin, user=world.zoya.user, role=role)
    services.add_comment(actor=world.zoya, task_id=task.pk, body="Вижу")


@pytest.mark.parametrize("body", ["", "   \n ", "x" * 5001])
def test_empty_and_oversized_comments_are_refused(world: World, body: str) -> None:  # noqa: F811
    task = make_task(world)
    with pytest.raises(DomainError) as error:
        services.add_comment(actor=world.anna, task_id=task.pk, body=body)
    assert error.value.code == "invalid_comment"


def test_archived_and_deleted_tasks_take_no_comments(world: World) -> None:  # noqa: F811
    archived = make_task(world)
    comment = services.add_comment(actor=world.anna, task_id=archived.pk, body="До архива")
    services.archive_task(actor=world.olga, task_id=archived.pk)
    with pytest.raises(DomainError) as error:
        services.add_comment(actor=world.anna, task_id=archived.pk, body="После")
    assert error.value.code == "task_archived"
    with pytest.raises(DomainError) as error:
        services.edit_comment(
            actor=world.anna, task_id=archived.pk, comment_id=comment.pk, body="Правка"
        )
    assert error.value.code == "task_archived"
    # Q24: the archive keeps the comments readable under the same access rules.
    assert list(services.comments(world.anna, archived)) == [comment]
    assert list(services.comments(world.boris, archived)) == []

    deleted = make_task(world)
    services.trash_task(actor=world.olga, task_id=deleted.pk)
    with pytest.raises(DomainError) as error:
        services.add_comment(actor=world.olga, task_id=deleted.pk, body="В корзине")
    assert error.value.code == "task_deleted"


# --- Editing ----------------------------------------------------------------


def test_author_edits_and_every_old_text_is_kept(world: World) -> None:  # noqa: F811
    task = make_task(world)
    comment = services.add_comment(actor=world.anna, task_id=task.pk, body="Первый")
    created_at = Comment.objects.get(pk=comment.pk).created_at

    services.edit_comment(actor=world.anna, task_id=task.pk, comment_id=comment.pk, body="Второй")
    edited = services.edit_comment(
        actor=world.anna, task_id=task.pk, comment_id=comment.pk, body="Третий"
    )

    assert (edited.body, edited.revision) == ("Третий", 3)
    assert edited.author_id == uid(world.anna)
    assert edited.edited_at is not None
    revisions = list(CommentRevision.objects.filter(comment=comment).order_by("revision"))
    assert [(r.revision, r.body) for r in revisions] == [(1, "Первый"), (2, "Второй")]
    assert revisions[0].written_at == created_at
    assert revisions[1].written_at == revisions[0].replaced_at
    assert all(r.replaced_by_id == uid(world.anna) for r in revisions)


def test_saving_the_same_text_is_not_an_edit(world: World) -> None:  # noqa: F811
    task = make_task(world)
    comment = services.add_comment(actor=world.anna, task_id=task.pk, body="Текст")
    same = services.edit_comment(
        actor=world.anna, task_id=task.pk, comment_id=comment.pk, body=" Текст "
    )
    assert (same.revision, same.edited_at) == (1, None)
    assert not CommentRevision.objects.exists()
    assert not AuditEvent.objects.filter(action="task.comment_edited").exists()


def test_nobody_edits_somebody_elses_comment(world: World) -> None:  # noqa: F811
    task = make_task(world)
    comment = services.add_comment(actor=world.anna, task_id=task.pk, body="Моё")
    # Not even the manager of the department.
    with pytest.raises(PermissionDeniedError):
        services.edit_comment(
            actor=world.olga, task_id=task.pk, comment_id=comment.pk, body="Чужое"
        )
    with pytest.raises(DomainError) as error:
        services.edit_comment(
            actor=world.boris, task_id=task.pk, comment_id=comment.pk, body="Чужое"
        )
    assert error.value.code == "task_not_found"
    assert Comment.objects.get(pk=comment.pk).body == "Моё"


def test_author_who_lost_access_to_the_task_cannot_edit(world: World) -> None:  # noqa: F811
    task = make_task(world)
    comment = services.add_comment(actor=world.anna, task_id=task.pk, body="Моё")
    services.reassign(actor=world.olga, task_id=task.pk, assignee_id=uid(world.boris))

    with pytest.raises(DomainError) as error:
        services.edit_comment(actor=world.anna, task_id=task.pk, comment_id=comment.pk, body="Ещё")

    assert error.value.code == "task_not_found"
    task = reload(task)
    assert list(services.comments(world.anna, task)) == []
    # The new assignee reads it and still cannot change it.
    assert list(services.comments(world.boris, task)) == [comment]
    with pytest.raises(PermissionDeniedError):
        services.edit_comment(actor=world.boris, task_id=task.pk, comment_id=comment.pk, body="Х")


def test_comment_of_another_task_is_not_found(world: World) -> None:  # noqa: F811
    task, other = make_task(world), make_task(world)
    comment = services.add_comment(actor=world.anna, task_id=other.pk, body="Там")
    for comment_id in (comment.pk, uuid4()):
        with pytest.raises(DomainError) as error:
            services.edit_comment(
                actor=world.anna, task_id=task.pk, comment_id=comment_id, body="Здесь"
            )
        assert error.value.code == "comment_not_found"


def test_database_refuses_inconsistent_comments(world: World) -> None:  # noqa: F811
    task = make_task(world)
    for fields in (
        {"body": ""},
        {"body": "x", "revision": 2},
        {"body": "x", "deleted_at": timezone.now()},
    ):
        with pytest.raises(IntegrityError), transaction.atomic():
            Comment.objects.create(task=task, author_id=uid(world.anna), **fields)


# --- Deleting (D038) --------------------------------------------------------


def test_manager_deletes_any_comment_and_it_disappears(world: World) -> None:  # noqa: F811
    task = make_task(world)
    kept = services.add_comment(actor=world.olga, task_id=task.pk, body="Остаётся")
    gone = services.add_comment(actor=world.anna, task_id=task.pk, body=SECRET_TEXT)

    services.delete_comment(actor=world.olga, task_id=task.pk, comment_id=gone.pk)

    assert list(services.comments(world.anna, task)) == [kept]
    stored = Comment.objects.get(pk=gone.pk)
    assert stored.deleted_at is not None
    assert stored.deleted_by_id == uid(world.olga)
    assert stored.body == SECRET_TEXT  # hidden, not erased
    event = AuditEvent.objects.get(action="task.comment_deleted")
    assert event.metadata["comment_id"] == str(gone.pk)
    assert event.metadata["author_id"] == str(uid(world.anna))
    assert SECRET_TEXT not in str(event.metadata)
    # A deleted comment can be neither edited nor deleted again.
    for operation in (
        lambda: services.edit_comment(
            actor=world.anna, task_id=task.pk, comment_id=gone.pk, body="Вернуть"
        ),
        lambda: services.delete_comment(actor=world.olga, task_id=task.pk, comment_id=gone.pk),
    ):
        with pytest.raises(DomainError) as error:
            operation()
        assert error.value.code == "comment_not_found"


def test_only_the_manager_deletes(world: World) -> None:  # noqa: F811
    assert "task.comment.delete" not in BASELINE_GRANTS
    assert DEPARTMENT_MANAGER_GRANTS["task.comment.delete"] is Scope.MANAGED_DEPARTMENTS
    task = make_task(world)
    comment = services.add_comment(actor=world.anna, task_id=task.pk, body="Моё")

    # Not the author, not the read-only superuser.
    for actor in (world.anna, world.zoya):
        with pytest.raises(PermissionDeniedError):
            services.delete_comment(actor=actor, task_id=task.pk, comment_id=comment.pk)
    # People who cannot see the task, a manager of another department included.
    for actor in (world.boris, world.pavel, world.vera):
        with pytest.raises(DomainError) as error:
            services.delete_comment(actor=actor, task_id=task.pk, comment_id=comment.pk)
        assert error.value.code == "task_not_found"
    assert Comment.objects.get(pk=comment.pk).deleted_at is None
    assert not AuditEvent.objects.filter(action="task.comment_deleted").exists()


def test_comment_of_an_archived_task_is_not_deleted(world: World) -> None:  # noqa: F811
    task = make_task(world)
    comment = services.add_comment(actor=world.anna, task_id=task.pk, body="Моё")
    services.archive_task(actor=world.olga, task_id=task.pk)
    with pytest.raises(DomainError) as error:
        services.delete_comment(actor=world.olga, task_id=task.pk, comment_id=comment.pk)
    assert error.value.code == "task_archived"


def test_api_delete_comment(
    team: dict[str, Employee],  # noqa: F811
    sales: Department,  # noqa: F811
) -> None:
    olga, anna = sign_in(team["olga"]), sign_in(team["anna"])
    task_id = new_task(olga, sales, team["anna"]).json()["id"]
    base = f"/api/v1/tasks/{task_id}"
    comment_id = call(anna, "post", f"{base}/comments", {"text": "Моё"}).json()["comments"][0]["id"]

    assert call(anna, "get", base).json()["actions"]["comment_delete"] is False
    assert call(anna, "delete", f"{base}/comments/{comment_id}").status_code == 403
    assert call(olga, "get", base).json()["actions"]["comment_delete"] is True
    deleted = call(olga, "delete", f"{base}/comments/{comment_id}")
    assert deleted.status_code == 200
    assert deleted.json()["comments"] == []
    assert call(olga, "delete", f"{base}/comments/{comment_id}").status_code == 404


# --- HTTP -------------------------------------------------------------------


def test_api_comment_round_trip(
    team: dict[str, Employee],  # noqa: F811
    sales: Department,  # noqa: F811
) -> None:
    olga, anna, boris = (sign_in(team[name]) for name in ("olga", "anna", "boris"))
    task_id = new_task(olga, sales, team["anna"]).json()["id"]
    base = f"/api/v1/tasks/{task_id}"

    added = call(anna, "post", f"{base}/comments", {"text": SECRET_TEXT})
    assert added.status_code == 200
    body = added.json()
    assert body["actions"]["comment"] is True
    (comment,) = body["comments"]
    assert comment["text"] == SECRET_TEXT
    assert comment["author"]["name"] == team["anna"].user.display_name
    assert comment["is_own"] is True
    assert comment["edited_at"] is None

    seen_by_manager = call(olga, "get", base).json()["comments"][0]
    assert seen_by_manager["is_own"] is False

    assert call(olga, "patch", f"{base}/comments/{comment['id']}", {"text": "Х"}).status_code == 403
    edited = call(anna, "patch", f"{base}/comments/{comment['id']}", {"text": "Исправлено"})
    assert edited.status_code == 200
    assert edited.json()["comments"][0]["text"] == "Исправлено"
    assert edited.json()["comments"][0]["edited_at"] is not None

    # A colleague from the same department: the task does not exist for them.
    assert call(boris, "get", base).status_code == 404
    assert call(boris, "post", f"{base}/comments", {"text": "Можно?"}).status_code == 404
    assert (
        call(boris, "patch", f"{base}/comments/{comment['id']}", {"text": "Х"}).status_code == 404
    )
    assert call(anna, "post", f"{base}/comments", {"text": "  "}).status_code == 400
    assert call(anna, "patch", f"{base}/comments/{uuid4()}", {"text": "Х"}).status_code == 404
    history = [entry["action"] for entry in call(anna, "get", base).json()["history"]]
    assert "task.comment_added" in history
    assert "task.comment_edited" in history


def test_api_comment_needs_a_session(sales: Department) -> None:  # noqa: F811
    from rest_framework.test import APIClient

    response = APIClient().post(f"/api/v1/tasks/{uuid4()}/comments", {"text": "x"}, format="json")
    assert response.status_code in (401, 403)
