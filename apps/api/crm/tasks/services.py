"""Task operations (S3; D005–D008, D015–D017, D019, Q02–Q09, Q19, Q24).

Every function authorizes its actor through `policy`, changes the task under a
row lock, bumps `row_version` and writes an audit event in the same transaction.

Rules that are easy to get wrong:

* The creator gets no access from authorship (Q02): `create_task` returns the
  task, but whether the creator may read it afterwards is `policy.allowed`.
* Entering a status of the `completed` category archives the task in the same
  transaction (D016). `cancelled` is not completion (Q04).
* Ticking checkpoints never changes the status (D015).
* A manual archive does not complete the task (Q05).
* An archived or deleted task is read-only: it has to be reopened or restored
  first. (PROVISIONAL — the mutation policy for such tasks is not approved.)
"""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.db.models import Max, Q, QuerySet
from django.utils import timezone

from crm.access import services as access
from crm.access.permissions import Scope
from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.identity.models import User
from crm.notifications import services as notifications
from crm.organization.models import Department, DepartmentMembership
from crm.projects import services as projects
from crm.projects.models import Project
from crm.tasks import policy
from crm.tasks.models import (
    Checkpoint,
    Comment,
    CommentRevision,
    Priority,
    StatusCategory,
    StatusTransition,
    Task,
    TaskStatus,
    TaskType,
)

OPEN_CATEGORIES = (StatusCategory.NEW, StatusCategory.ACTIVE)


class StaleTaskError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "task_changed", "The task was changed by somebody else. Reload it and try again."
        )


# --- Helpers ----------------------------------------------------------------


def _log(actor: Actor, action: str, task: Task, **metadata: object) -> None:
    # Titles and descriptions are never copied into the audit log.
    audit.record(
        actor=actor,
        action=action,
        entity_type="task",
        entity_id=str(task.pk),
        metadata={"department_id": str(task.responsible_department_id), **metadata},
    )


def _locked(actor: Actor, task_id: UUID) -> Task:
    """Lock a task the actor may see. A task outside their reach does not exist for them."""
    task = policy.readable(actor).select_for_update(of=("self",)).filter(pk=task_id).first()
    if task is None:
        raise DomainError("task_not_found", "No such task.")
    return task


def _require_editable(task: Task) -> None:
    if task.deleted_at is not None:
        raise DomainError("task_deleted", "The task is in the trash. Restore it first.")
    if task.archived_at is not None:
        raise DomainError("task_archived", "The task is archived. Reopen it first.")


def _check_version(task: Task, expected_version: int | None) -> None:
    if expected_version is not None and expected_version != task.row_version:
        raise StaleTaskError


def _save(task: Task, *fields: str) -> None:
    task.row_version += 1
    task.save(update_fields=[*fields, "row_version", "updated_at"])


def _clean_title(raw: str) -> str:
    title = " ".join(raw.split())
    if not title:
        raise DomainError("invalid_title", "The task needs a title.")
    if len(title) > 200:
        raise DomainError("invalid_title", "The title is too long.")
    return title


def _eligible_users(department_id: UUID) -> QuerySet[User]:
    """D037: a task of a department is assigned to one of its active people —
    an employee who belongs to it or a manager who manages it."""
    return User.objects.filter(
        Q(department_memberships__department_id=department_id)
        | Q(managed_departments__department_id=department_id),
        is_active=True,
    ).distinct()


def _eligible_assignee(department: Department, assignee_id: UUID) -> User:
    user = _eligible_users(department.pk).filter(pk=assignee_id).first()
    if user is None:
        raise DomainError(
            "assignee_not_eligible",
            "The assignee must be an active employee or manager of the responsible department.",
        )
    return user


# --- Reading ----------------------------------------------------------------


def statuses() -> QuerySet[TaskStatus]:
    return TaskStatus.objects.filter(is_active=True)


def board(actor: Actor, *, view: str) -> QuerySet[Task]:
    """Tasks for one of the screens. The read scope is always applied first.

    mine    — active tasks assigned to the actor (the personal board);
    all     — every active task the actor may see;
    archive — archived tasks (Q24: open to every employee, within their scope);
    trash   — deleted tasks, only where the actor may restore them.
    """
    if actor.user is None:
        return Task.objects.none()
    tasks = policy.readable(actor).select_related(
        "status", "assignee", "responsible_department", "author", "project"
    )
    if view == "mine":
        return tasks.filter(
            assignee_id=actor.user.pk, archived_at__isnull=True, deleted_at__isnull=True
        )
    if view == "all":
        return tasks.filter(archived_at__isnull=True, deleted_at__isnull=True)
    if view == "archive":
        return tasks.filter(archived_at__isnull=False, deleted_at__isnull=True)
    if view == "trash":
        scope = access.scope_for(actor, "task.delete")
        if scope is None:
            return Task.objects.none()
        deleted = tasks.filter(deleted_at__isnull=False)
        if scope is Scope.COMPANY:
            return deleted
        return deleted.filter(
            responsible_department_id__in=access.managed_department_ids(actor.user)
        )
    raise DomainError("unknown_view", "Unknown task view.")


def get_task(actor: Actor, task_id: UUID) -> Task:
    task = (
        policy.readable(actor)
        .select_related("status", "assignee", "responsible_department", "author", "project")
        .filter(pk=task_id)
        .first()
    )
    if task is None:
        raise DomainError("task_not_found", "No such task.")
    if task.deleted_at is not None and not policy.allowed(actor, "task.delete", task):
        # The trash is visible only to those who may restore from it.
        raise DomainError("task_not_found", "No such task.")
    return task


def assignable_departments(actor: Actor) -> QuerySet[Department]:
    """Departments the actor may create tasks for (D037): the managed ones, or
    every open department for a company-wide grant."""
    scope = access.require_department_scope(actor, "task.create")
    departments = Department.objects.filter(is_active=True).order_by("name")
    if scope.company:
        return departments
    return departments.filter(pk__in=scope.department_ids)


def eligible_assignees(actor: Actor, department_id: UUID) -> QuerySet[User]:
    """Whom a task of this department may be assigned to (names only). Asked by
    whoever creates tasks for the department or reassigns them in it."""
    if not (
        access.department_scope(actor, "task.create").covers(department_id)
        or access.department_scope(actor, "task.reassign").covers(department_id)
    ):
        raise PermissionDeniedError()
    if not Department.objects.filter(pk=department_id, is_active=True).exists():
        return User.objects.none()
    return _eligible_users(department_id).order_by("display_name")


# --- Creating ---------------------------------------------------------------


def create_task(
    *,
    actor: Actor,
    title: str,
    department_id: UUID,
    assignee_id: UUID,
    description: str = "",
    priority: str = Priority.NORMAL,
    due_at: datetime | None = None,
    task_type: str = TaskType.TASK,
    project_id: UUID | None = None,
    checkpoints: Sequence[str] = (),
) -> Task:
    """Create a task that is assigned at once, without anybody's approval (D006).
    `checkpoints` are the ones a request template provides (already validated)."""
    # D037: a manager creates tasks, and only for a department they manage.
    access.require_in_department(actor, "task.create", department_id)
    if actor.user is None:
        raise PermissionDeniedError()
    clean_title = _clean_title(title)
    if priority not in Priority.values:
        raise DomainError("invalid_priority", "Unknown priority.")
    if task_type not in TaskType.values:
        raise DomainError("invalid_task_type", "Unknown task type.")

    with transaction.atomic():
        department = Department.objects.filter(pk=department_id, is_active=True).first()
        if department is None:
            raise DomainError("department_not_found", "No such open department.")
        assignee = _eligible_assignee(department, assignee_id)
        project = _selectable_project(actor, project_id) if project_id else None
        first_status = (
            TaskStatus.objects.filter(is_active=True, category=StatusCategory.NEW)
            .order_by("position")
            .first()
        )
        if first_status is None:
            raise DomainError("no_initial_status", "No starting status is configured.")
        now = timezone.now()
        task = Task.objects.create(
            task_type=task_type,
            title=clean_title,
            description=description.strip(),
            priority=priority,
            responsible_department=department,
            project=project,
            author=actor.user,
            assignee=assignee,
            assigned_at=now,
            status=first_status,
            due_at=due_at,
            original_due_at=due_at,
        )
        Checkpoint.objects.bulk_create(
            Checkpoint(task=task, label=label, position=position)
            for position, label in enumerate(checkpoints, start=1)
        )
        _log(actor, "task.created", task, assignee_id=str(assignee.pk), task_type=task_type)
        notifications.task_assigned(task=task, actor=actor)
    return task


# --- Editing ----------------------------------------------------------------


def update_content(
    *,
    actor: Actor,
    task_id: UUID,
    title: str | None = None,
    description: str | None = None,
    expected_version: int | None = None,
) -> Task:
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.update", task)
        _require_editable(task)
        _check_version(task, expected_version)
        changed = []
        if title is not None and (clean := _clean_title(title)) != task.title:
            task.title = clean
            changed.append("title")
        if description is not None and description.strip() != task.description:
            task.description = description.strip()
            changed.append("description")
        if changed:
            _save(task, *changed)
            _log(actor, "task.content_changed", task, fields=changed)
    return task


def change_deadline(
    *, actor: Actor, task_id: UUID, due_at: datetime | None, expected_version: int | None = None
) -> Task:
    """D017: the assignee may move the deadline; both values are kept in history
    and the department's managers are notified."""
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.deadline", task)
        _require_editable(task)
        _check_version(task, expected_version)
        if due_at != task.due_at:
            before = task.due_at
            task.due_at = due_at
            fields = ["due_at"]
            if task.original_due_at is None and due_at is not None:
                task.original_due_at = due_at
                fields.append("original_due_at")
            _save(task, *fields)
            _log(
                actor,
                "task.deadline_changed",
                task,
                before=before.isoformat() if before else None,
                after=due_at.isoformat() if due_at else None,
            )
            notifications.deadline_changed(task=task, actor=actor)
    return task


def change_priority(
    *, actor: Actor, task_id: UUID, priority: str, expected_version: int | None = None
) -> Task:
    if priority not in Priority.values:
        raise DomainError("invalid_priority", "Unknown priority.")
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.priority", task)
        _require_editable(task)
        _check_version(task, expected_version)
        if priority != task.priority:
            before = task.priority
            task.priority = priority
            _save(task, "priority")
            _log(actor, "task.priority_changed", task, before=before, after=priority)
    return task


def selectable_projects(actor: Actor) -> QuerySet[Project]:
    """Projects a task may be put into by this actor: the open projects they can
    see (those of their departments and those their employees take part in).

    PROVISIONAL (docs/OPEN_QUESTIONS.md): the assignee need not take part in the
    project, and the task's department need not be the project's.
    """
    if not (
        access.department_scope(actor, "task.create")
        or access.department_scope(actor, "task.project")
    ):
        raise PermissionDeniedError()
    return projects.visible_projects(actor).filter(is_active=True).order_by("name")


def _selectable_project(actor: Actor, project_id: UUID) -> Project:
    project = selectable_projects(actor).filter(pk=project_id).first()
    if project is None:
        raise DomainError("project_not_found", "No such open project.")
    return project


def change_project(
    *,
    actor: Actor,
    task_id: UUID,
    project_id: UUID | None,
    expected_version: int | None = None,
) -> Task:
    """Put the task into a project or take it out (`project_id=None`). The
    manager's field, like priority. Access to the task does not change (D003)."""
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.project", task)
        _require_editable(task)
        _check_version(task, expected_version)
        if project_id != task.project_id:
            before = task.project_id
            task.project = _selectable_project(actor, project_id) if project_id else None
            _save(task, "project")
            _log(
                actor,
                "task.project_changed",
                task,
                before=str(before) if before else None,
                after=str(project_id) if project_id else None,
            )
    return task


def reassign(
    *, actor: Actor, task_id: UUID, assignee_id: UUID, expected_version: int | None = None
) -> Task:
    """D007: only a manager of the task's department or a specially authorized
    superuser changes the assignee. A new assignment cycle starts (Q18)."""
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.reassign", task)
        _require_editable(task)
        _check_version(task, expected_version)
        if assignee_id != task.assignee_id:
            assignee = _eligible_assignee(task.responsible_department, assignee_id)
            before = task.assignee_id
            task.assignee = assignee
            task.assigned_at = timezone.now()
            _save(task, "assignee", "assigned_at")
            _log(actor, "task.reassigned", task, before=str(before), after=str(assignee.pk))
            notifications.task_assigned(task=task, actor=actor)
    return task


# --- Status, archive, trash -------------------------------------------------


def change_status(
    *, actor: Actor, task_id: UUID, status_id: UUID, expected_version: int | None = None
) -> Task:
    """Move the task along an allowed transition. Completion archives it at once."""
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.status", task)
        _require_editable(task)
        _check_version(task, expected_version)
        if status_id == task.status_id:
            return task
        target = TaskStatus.objects.filter(pk=status_id, is_active=True).first()
        if (
            target is None
            or not StatusTransition.objects.filter(
                from_status_id=task.status_id, to_status=target
            ).exists()
        ):
            raise DomainError(
                "transition_not_allowed", "The task cannot be moved to this status from here."
            )
        before = task.status_id
        fields = ["status"]
        if target.category == StatusCategory.COMPLETED:
            now = timezone.now()
            task.status_before_completion_id = before
            task.completed_at = now
            task.archived_at = now
            fields += ["status_before_completion", "completed_at", "archived_at"]
        task.status = target
        _save(task, *fields)
        _log(
            actor,
            "task.completed" if task.completed_at else "task.status_changed",
            task,
            before=str(before),
            after=str(target.pk),
        )
    return task


def archive_task(*, actor: Actor, task_id: UUID) -> Task:
    """Q05: a manager or an authorized superuser archives an unfinished task.
    The task is not completed by this and counts in no completion figure."""
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.archive", task)
        _require_editable(task)
        task.archived_at = timezone.now()
        _save(task, "archived_at")
        _log(actor, "task.archived", task, completed=False)
    return task


def reopen_task(*, actor: Actor, task_id: UUID) -> Task:
    """Bring an archived task back to the board (Q05).

    A completed task returns to the status it had before completion; if that
    status no longer exists the reopening is refused — a replacement is never
    picked automatically (Q07). A manually archived task simply leaves the archive.
    """
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.archive", task)
        if task.deleted_at is not None:
            raise DomainError("task_deleted", "The task is in the trash. Restore it first.")
        if task.archived_at is None:
            raise DomainError("task_not_archived", "The task is not archived.")
        fields = ["archived_at"]
        was_completed = task.completed_at is not None
        if was_completed:
            previous = task.status_before_completion
            if (
                previous is None
                or not previous.is_active
                or previous.category not in OPEN_CATEGORIES
            ):
                raise DomainError(
                    "previous_status_unavailable",
                    "The status the task had before completion no longer exists.",
                )
            task.status = previous
            task.status_before_completion = None
            task.completed_at = None
            fields += ["status", "status_before_completion", "completed_at"]
        task.archived_at = None
        _save(task, *fields)
        _log(actor, "task.reopened", task, was_completed=was_completed)
    return task


def trash_task(*, actor: Actor, task_id: UUID) -> Task:
    """Soft delete (Q06). Nothing is removed; the trash never empties by itself."""
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.delete", task)
        if task.deleted_at is not None or actor.user is None:
            return task
        task.deleted_at = timezone.now()
        task.deleted_by = actor.user
        _save(task, "deleted_at", "deleted_by")
        _log(actor, "task.trashed", task)
    return task


def restore_task(*, actor: Actor, task_id: UUID) -> Task:
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.delete", task)
        if task.deleted_at is None:
            return task
        task.deleted_at = None
        task.deleted_by = None
        _save(task, "deleted_at", "deleted_by")
        _log(actor, "task.restored", task)
    return task


# --- Checkpoints ------------------------------------------------------------


def add_checkpoint(*, actor: Actor, task_id: UUID, label: str) -> Checkpoint:
    clean = " ".join(label.split())
    if not clean or len(clean) > 200:
        raise DomainError(
            "invalid_checkpoint", "A checkpoint needs a text of up to 200 characters."
        )
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.checkpoints.use", task)
        _require_editable(task)
        last = task.checkpoints.aggregate(last=Max("position"))["last"] or 0
        checkpoint = Checkpoint.objects.create(task=task, label=clean, position=last + 1)
        _save(task)
        _log(actor, "task.checkpoint_added", task, checkpoint_id=str(checkpoint.pk))
    return checkpoint


def set_checkpoint_done(
    *, actor: Actor, task_id: UUID, checkpoint_id: UUID, done: bool
) -> Checkpoint:
    """Tick or untick. The task's status is not touched, whatever the result (D015)."""
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.checkpoints.use", task)
        _require_editable(task)
        checkpoint = Checkpoint.objects.filter(pk=checkpoint_id, task=task).first()
        if checkpoint is None or actor.user is None:
            raise DomainError("checkpoint_not_found", "No such checkpoint.")
        if checkpoint.is_done != done:
            checkpoint.is_done = done
            checkpoint.done_by = actor.user if done else None
            checkpoint.done_at = timezone.now() if done else None
            checkpoint.save(update_fields=["is_done", "done_by", "done_at"])
            _save(task)
            _log(
                actor,
                "task.checkpoint_done" if done else "task.checkpoint_undone",
                task,
                checkpoint_id=str(checkpoint.pk),
            )
    return checkpoint


def remove_checkpoint(*, actor: Actor, task_id: UUID, checkpoint_id: UUID) -> None:
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.checkpoints.manage", task)
        _require_editable(task)
        deleted, _ = Checkpoint.objects.filter(pk=checkpoint_id, task=task).delete()
        if not deleted:
            raise DomainError("checkpoint_not_found", "No such checkpoint.")
        _save(task)
        _log(actor, "task.checkpoint_removed", task, checkpoint_id=str(checkpoint_id))


# --- Deactivation hand-over (D019, Q08) -------------------------------------


# --- Comments ---------------------------------------------------------------

COMMENT_MAX_LENGTH = 5000


def _clean_comment(raw: str) -> str:
    body = raw.replace("\r\n", "\n").strip()
    if not body or len(body) > COMMENT_MAX_LENGTH:
        raise DomainError(
            "invalid_comment", f"A comment needs a text of up to {COMMENT_MAX_LENGTH} characters."
        )
    return body


def _live_comment(task: Task, comment_id: UUID) -> Comment:
    comment = (
        Comment.objects.select_for_update()
        .filter(pk=comment_id, task=task, deleted_at__isnull=True)
        .first()
    )
    if comment is None:
        raise DomainError("comment_not_found", "No such comment.")
    return comment


def comments(actor: Actor, task: Task) -> QuerySet[Comment]:
    """Comments of a task the actor may see. Everybody who sees the task reads them."""
    if not policy.allowed(actor, policy.READ, task):
        return Comment.objects.none()
    return task.comments.filter(deleted_at__isnull=True).select_related("author")


def add_comment(*, actor: Actor, task_id: UUID, body: str) -> Comment:
    """Q19: the assignee and the manager comment. The comment's text is never
    copied into the audit log."""
    clean = _clean_comment(body)
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.comment", task)
        _require_editable(task)
        if actor.user is None:  # unreachable: only a user holds a task permission
            raise PermissionDeniedError()
        comment = Comment.objects.create(task=task, author=actor.user, body=clean)
        _log(actor, "task.comment_added", task, comment_id=str(comment.pk))
        notifications.comment_added(task=task, actor=actor)
    return comment


def edit_comment(*, actor: Actor, task_id: UUID, comment_id: UUID, body: str) -> Comment:
    """Only the author edits a comment, and only while they still may comment on
    the task. The previous text is kept as a revision.

    D038: there is no time limit for editing.
    """
    clean = _clean_comment(body)
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.comment", task)
        _require_editable(task)
        comment = _live_comment(task, comment_id)
        if actor.user is None or comment.author_id != actor.user.pk:
            raise PermissionDeniedError()
        if clean == comment.body:
            return comment
        now = timezone.now()
        CommentRevision.objects.create(
            comment=comment,
            revision=comment.revision,
            body=comment.body,
            written_at=comment.edited_at or comment.created_at,
            replaced_at=now,
            replaced_by=actor.user,
        )
        comment.body = clean
        comment.revision += 1
        comment.edited_at = now
        comment.save(update_fields=["body", "revision", "edited_at"])
        _log(
            actor,
            "task.comment_edited",
            task,
            comment_id=str(comment.pk),
            revision=comment.revision,
        )
    return comment


def delete_comment(*, actor: Actor, task_id: UUID, comment_id: UUID) -> None:
    """D038: the manager of the task's department removes a comment — anybody's.
    The author alone cannot. The row stays in the database, hidden from everybody."""
    with transaction.atomic():
        task = _locked(actor, task_id)
        policy.require(actor, "task.comment.delete", task)
        _require_editable(task)
        comment = _live_comment(task, comment_id)
        if actor.user is None:  # unreachable: only a user holds a task permission
            raise PermissionDeniedError()
        comment.deleted_at = timezone.now()
        comment.deleted_by = actor.user
        comment.save(update_fields=["deleted_at", "deleted_by"])
        _log(
            actor,
            "task.comment_deleted",
            task,
            comment_id=str(comment.pk),
            author_id=str(comment.author_id),
        )


def hand_over_open_tasks(*, actor: Actor, user: User) -> int:
    """Give the open tasks of an employee who is being deactivated to the
    designated manager of their primary department.

    Runs inside the deactivation transaction. If the employee has open tasks and
    there is nobody to take them, the deactivation is refused: nothing is ever
    reassigned to an arbitrary person. (The superuser fallback of Q08 needs a
    designated superuser, which is not configured yet.)
    """
    open_tasks = Task.objects.select_for_update().filter(
        assignee_id=user.pk,
        archived_at__isnull=True,
        deleted_at__isnull=True,
        status__category__in=OPEN_CATEGORIES,
    )
    tasks = list(open_tasks)
    if not tasks:
        return 0
    primary = DepartmentMembership.objects.filter(user_id=user.pk, is_primary=True).first()
    target = (
        User.objects.filter(
            is_active=True,
            managed_departments__department_id=primary.department_id,
            managed_departments__is_designated=True,
        )
        .exclude(pk=user.pk)
        .first()
        if primary is not None
        else None
    )
    if target is None:
        raise DomainError(
            "handover_target_missing",
            "The employee has open tasks and their primary department has no other "
            "designated manager to take them. Assign one first.",
        )
    now = timezone.now()
    for task in tasks:
        task.assignee = target
        task.assigned_at = now
        _save(task, "assignee", "assigned_at")
        _log(
            actor,
            "task.reassigned",
            task,
            before=str(user.pk),
            after=str(target.pk),
            reason="deactivation",
        )
        notifications.task_assigned(task=task, actor=actor)
    return len(tasks)
