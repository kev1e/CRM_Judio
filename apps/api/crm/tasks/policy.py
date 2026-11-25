"""Who may see and do what with a task. The only place that decides it.

For a task permission the scopes are cumulative:

* OWN — tasks assigned to the user;
* MANAGED_DEPARTMENTS — those, plus tasks whose responsible department the user
  manages (only the task's own department counts, D008);
* COMPANY — every task.

Being the author, belonging to the task's department or to a project gives
nothing (Q02). Everything is read from the database on each check (D020).
"""

from django.db.models import Q, QuerySet

from crm.access import services as access
from crm.access.permissions import Scope
from crm.common.actors import Actor
from crm.common.exceptions import PermissionDeniedError
from crm.tasks.models import Task

READ = "task.read"


def _reach(actor: Actor, code: str) -> Q | None:
    """Filter of the tasks on which the actor holds `code`; None when on none."""
    scope = access.scope_for(actor, code)
    if scope is None or actor.user is None:
        return None
    if scope is Scope.COMPANY:
        return Q()
    own = Q(assignee_id=actor.user.pk)
    if scope is Scope.MANAGED_DEPARTMENTS:
        managed = access.managed_department_ids(actor.user)
        return own | Q(responsible_department_id__in=managed)
    return own


def allowed(actor: Actor, code: str, task: Task) -> bool:
    """Whether the actor holds `code` on this task (for a task they can see)."""
    scope = access.scope_for(actor, code)
    if scope is None or actor.user is None:
        return False
    if scope is Scope.COMPANY:
        return True
    if task.assignee_id == actor.user.pk:
        return True
    return scope is Scope.MANAGED_DEPARTMENTS and (
        task.responsible_department_id in access.managed_department_ids(actor.user)
    )


def require(actor: Actor, code: str, task: Task) -> None:
    """Refuse unless the actor may both see the task and perform `code` on it."""
    if not (allowed(actor, READ, task) and allowed(actor, code, task)):
        raise PermissionDeniedError()


def readable(actor: Actor) -> QuerySet[Task]:
    """Every task the actor may see, in any state. The scope is applied in the
    database query; callers narrow it further (active, archived, deleted)."""
    reach = _reach(actor, READ)
    if reach is None:
        return Task.objects.none()
    return Task.objects.filter(reach)


def actions(actor: Actor, task: Task) -> dict[str, bool]:
    """What the interface may offer for this task. A hint for the UI only: every
    operation is checked again by its service."""
    codes = (
        "task.update",
        "task.status",
        "task.deadline",
        "task.checkpoints.use",
        "task.checkpoints.manage",
        "task.priority",
        "task.reassign",
        "task.archive",
        "task.delete",
    )
    return {code: allowed(actor, code, task) for code in codes}
