"""Statuses and the moves between them — the administrator's configuration
(D005, Q04, Q09; `retire_status` of docs/ARCHITECTURE.md).

Everything here needs `workflow.manage`. That permission configures the board
and shows how many tasks sit in each status; it never shows a task (D003).

* A status is never deleted, it is retired (`is_active = False`). Old audit
  events keep pointing at it, and it can be brought back.
* Retiring a status that tasks still use needs an explicit replacement chosen by
  the administrator. Nothing is matched by name or position.
* A category is fixed when the status is created: changing it afterwards could
  complete or un-complete tasks in bulk.

PROVISIONAL (docs/OPEN_QUESTIONS.md): which replacements are "safe". Until the
owner decides otherwise a replacement must be of the same kind — an open status
(new / active) for an open one, completed for completed, cancelled for
cancelled — so that retiring a status never completes, cancels or reopens tasks.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from django.db import transaction
from django.db.models import Count, F, Max

from crm.access import services as access
from crm.access.permissions import Scope
from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.tasks.models import StatusCategory, StatusTransition, Task, TaskStatus

_MANAGE = "workflow.manage"
_OPEN = (StatusCategory.NEW, StatusCategory.ACTIVE)


@dataclass(frozen=True, slots=True)
class StatusInfo:
    status: TaskStatus
    next_status_ids: list[UUID]
    task_count: int


def _require_manage(actor: Actor) -> None:
    access.require_permission(actor, _MANAGE, at_least=Scope.COMPANY)


def _log(actor: Actor, action: str, status: TaskStatus, **metadata: object) -> None:
    audit.record(
        actor=actor,
        action=action,
        entity_type="task_status",
        entity_id=str(status.pk),
        metadata={"name": status.name, "category": status.category, **metadata},
    )


def _clean_name(raw: str, *, except_id: UUID | None = None) -> str:
    name = " ".join(raw.split())
    if not name:
        raise DomainError("invalid_status_name", "The status needs a name.")
    if len(name) > 80:
        raise DomainError("invalid_status_name", "The status name is too long.")
    taken = TaskStatus.objects.filter(name__iexact=name)
    if except_id is not None:
        taken = taken.exclude(pk=except_id)
    if taken.exists():
        raise DomainError("status_name_taken", "A status with this name already exists.")
    return name


def _lock_all() -> dict[UUID, TaskStatus]:
    """Configuration changes are rare; they simply take turns."""
    return {s.pk: s for s in TaskStatus.objects.select_for_update().order_by("position", "name")}


def _get(statuses: dict[UUID, TaskStatus], status_id: UUID) -> TaskStatus:
    status = statuses.get(status_id)
    if status is None:
        raise DomainError("status_not_found", "No such status.")
    return status


def _same_kind(a: str, b: str) -> bool:
    return a == b or (a in _OPEN and b in _OPEN)


# --- Reading ----------------------------------------------------------------


def configuration(*, actor: Actor) -> list[StatusInfo]:
    """Every status, retired ones included, with its moves and a task count."""
    _require_manage(actor)
    moves: dict[UUID, list[UUID]] = {}
    for source, target in StatusTransition.objects.filter(to_status__is_active=True).values_list(
        "from_status_id", "to_status_id"
    ):
        moves.setdefault(source, []).append(target)
    counts = dict(
        Task.objects.values_list("status_id").annotate(n=Count("pk")).values_list("status_id", "n")
    )
    return [
        StatusInfo(status=s, next_status_ids=moves.get(s.pk, []), task_count=counts.get(s.pk, 0))
        for s in TaskStatus.objects.order_by(F("is_active").desc(), "position", "name")
    ]


# --- Changes ----------------------------------------------------------------


def create_status(*, actor: Actor, name: str, category: str) -> TaskStatus:
    _require_manage(actor)
    if category not in StatusCategory.values:
        raise DomainError("invalid_status_category", "Unknown status category.")
    with transaction.atomic():
        _lock_all()
        clean = _clean_name(name)
        last = TaskStatus.objects.aggregate(last=Max("position"))["last"] or 0
        status = TaskStatus.objects.create(name=clean, category=category, position=last + 10)
        _log(actor, "task_status.created", status)
    return status


def rename_status(*, actor: Actor, status_id: UUID, name: str) -> TaskStatus:
    _require_manage(actor)
    with transaction.atomic():
        status = _get(_lock_all(), status_id)
        clean = _clean_name(name, except_id=status.pk)
        if clean != status.name:
            before = status.name
            status.name = clean
            status.save(update_fields=["name"])
            _log(actor, "task_status.renamed", status, before=before)
    return status


def set_moves(*, actor: Actor, status_id: UUID, next_status_ids: Sequence[UUID]) -> TaskStatus:
    """Replace the list of statuses a task may be moved to from this one."""
    _require_manage(actor)
    with transaction.atomic():
        statuses = _lock_all()
        status = _get(statuses, status_id)
        if not status.is_active:
            raise DomainError("status_retired", "The status is retired.")
        wanted = set(next_status_ids)
        if status.pk in wanted:
            raise DomainError("invalid_moves", "A status cannot lead to itself.")
        for target_id in wanted:
            if not _get(statuses, target_id).is_active:
                raise DomainError("invalid_moves", "A move cannot lead to a retired status.")
        if wanted and status.category == StatusCategory.COMPLETED:
            # A completed task is archived and read-only; it returns through "reopen" (Q05).
            raise DomainError(
                "invalid_moves", "A completed task is returned by reopening, not by a move."
            )
        current = set(
            StatusTransition.objects.filter(
                from_status=status, to_status__is_active=True
            ).values_list("to_status_id", flat=True)
        )
        if wanted != current:
            StatusTransition.objects.filter(
                from_status=status, to_status_id__in=current - wanted
            ).delete()
            StatusTransition.objects.bulk_create(
                [
                    StatusTransition(from_status=status, to_status_id=target_id)
                    for target_id in wanted - current
                ],
                ignore_conflicts=True,
            )
            _log(
                actor,
                "task_status.moves_changed",
                status,
                added=sorted(str(i) for i in wanted - current),
                removed=sorted(str(i) for i in current - wanted),
            )
    return status


def reorder(*, actor: Actor, status_ids: Sequence[UUID]) -> None:
    """Set the order of the board's columns. Every active status must be listed once."""
    _require_manage(actor)
    with transaction.atomic():
        statuses = _lock_all()
        active = {pk for pk, s in statuses.items() if s.is_active}
        if len(status_ids) != len(set(status_ids)) or set(status_ids) != active:
            raise DomainError("invalid_order", "List every active status exactly once.")
        for index, status_id in enumerate(status_ids, start=1):
            status = statuses[status_id]
            if status.position != index * 10:
                status.position = index * 10
                status.save(update_fields=["position"])
        audit.record(
            actor=actor,
            action="task_status.reordered",
            entity_type="task_status",
            entity_id="*",
            metadata={"order": [str(i) for i in status_ids]},
        )


def retire_status(*, actor: Actor, status_id: UUID, replacement_id: UUID | None = None) -> int:
    """Take a status off the board. Tasks that use it move to `replacement_id`.

    Returns how many tasks were moved. Each moved task gets its own history
    entry; earlier events keep the retired status' ID.
    """
    _require_manage(actor)
    with transaction.atomic():
        statuses = _lock_all()
        status = _get(statuses, status_id)
        if not status.is_active:
            raise DomainError("status_retired", "The status is already retired.")
        if status.category == StatusCategory.NEW and not any(
            s.is_active and s.category == StatusCategory.NEW and s.pk != status.pk
            for s in statuses.values()
        ):
            raise DomainError(
                "last_new_status", "New tasks need at least one status of the “new” category."
            )
        affected = Task.objects.select_for_update().filter(status=status)
        remembered = Task.objects.select_for_update().filter(status_before_completion=status)
        task_ids = list(affected.values_list("pk", "responsible_department_id"))
        in_use = bool(task_ids) or remembered.exists()
        replacement: TaskStatus | None = None
        if replacement_id is not None:
            replacement = _get(statuses, replacement_id)
            if replacement.pk == status.pk or not replacement.is_active:
                raise DomainError(
                    "invalid_replacement", "Choose another active status as the replacement."
                )
            if not _same_kind(status.category, replacement.category):
                raise DomainError(
                    "unsafe_replacement",
                    "The replacement must be of the same kind, so that no task is "
                    "completed, cancelled or reopened by this.",
                )
        elif in_use:
            raise DomainError(
                "replacement_required", "Tasks use this status. Choose a replacement for them."
            )
        if replacement is not None:
            affected.update(status=replacement, row_version=F("row_version") + 1)
            remembered.update(status_before_completion=replacement)
            for task_id, department_id in task_ids:
                audit.record(
                    actor=actor,
                    action="task.status_remapped",
                    entity_type="task",
                    entity_id=str(task_id),
                    metadata={
                        "department_id": str(department_id),
                        "before": str(status.pk),
                        "after": str(replacement.pk),
                    },
                )
        status.is_active = False
        status.save(update_fields=["is_active"])
        _log(
            actor,
            "task_status.retired",
            status,
            replacement_id=str(replacement.pk) if replacement else None,
            replacement_name=replacement.name if replacement else None,
            moved_tasks=len(task_ids),
        )
    return len(task_ids)


def restore_status(*, actor: Actor, status_id: UUID) -> TaskStatus:
    """Bring a retired status back to the board. Tasks moved away from it stay
    where they are."""
    _require_manage(actor)
    with transaction.atomic():
        statuses = _lock_all()
        status = _get(statuses, status_id)
        if status.is_active:
            raise DomainError("status_active", "The status is not retired.")
        last = max((s.position for s in statuses.values() if s.is_active), default=0)
        status.is_active = True
        status.position = last + 10
        status.save(update_fields=["is_active", "position"])
        # Moves into statuses retired meanwhile stay hidden until those return.
        _log(actor, "task_status.restored", status)
    return status
