"""Telegram notifications about tasks (S6; D012, D017, Q23).

* A notification is a row of the outbox, written in the same transaction as the
  change; a Celery task sends it after the commit. A change that is rolled back
  notifies nobody, and Telegram being down never fails the change.
* Nothing is decided when the row is written except who *might* be told. Right
  before sending, everything is read again: the recipient must still be active,
  bound to Telegram and **able to read the task** (Q23: "re-check at dispatch").
  Otherwise the message is skipped.
* The text is composed at that moment and stored nowhere. A comment's text is
  never sent — the message only says that there is one.

PROVISIONAL (docs/OPEN_QUESTIONS.md): who is told about what, the wording, the
retry schedule, the time zone of dates in messages. Mentions, status and
checkpoint notifications, project invitations, digests, the user's own settings
and in-CRM notifications are not built.
"""

import logging
from collections.abc import Iterable
from uuid import UUID
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from crm.common.actors import Actor
from crm.identity.models import User
from crm.notifications.models import Kind, Notification, Status
from crm.organization.models import DepartmentManager
from crm.tasks import policy
from crm.tasks.models import Task
from crm.telegram import texts
from crm.telegram.gateway import (
    TaskMessage,
    TelegramRefusedError,
    TelegramUnavailableError,
    get_gateway,
)

logger = logging.getLogger(__name__)


# --- Writing to the outbox (called by domain services, inside their transaction)


def _enqueue(notification_id: UUID) -> None:
    from crm.notifications.tasks import deliver_notification

    try:
        deliver_notification.delay(str(notification_id))
    except Exception:
        # The queue is down. The row stays pending; the change itself succeeded.
        logger.exception("Could not enqueue notification %s", notification_id)


def _notify(kind: Kind, task: Task, actor: Actor, recipient_ids: Iterable[UUID]) -> None:
    author_id = actor.user.pk if actor.user else None
    # Nobody is told about what they did themselves.
    wanted = {pk for pk in recipient_ids if pk != author_id}
    for recipient_id in sorted(wanted):
        notification = Notification.objects.create(
            recipient_id=recipient_id, kind=kind, task=task, actor=actor.user
        )
        transaction.on_commit(lambda pk=notification.pk: _enqueue(pk))  # type: ignore[misc]


def _manager_ids(task: Task) -> set[UUID]:
    return set(
        DepartmentManager.objects.filter(
            department_id=task.responsible_department_id, user__is_active=True
        ).values_list("user_id", flat=True)
    )


def task_assigned(*, task: Task, actor: Actor) -> None:
    """A task was created for somebody or handed to somebody else."""
    _notify(Kind.TASK_ASSIGNED, task, actor, [task.assignee_id])


def deadline_changed(*, task: Task, actor: Actor) -> None:
    """D017: the assignee moved the deadline — the department's managers are
    told; when a manager moved it, the assignee is told."""
    _notify(Kind.DEADLINE_CHANGED, task, actor, _manager_ids(task) | {task.assignee_id})


def comment_added(*, task: Task, actor: Actor) -> None:
    _notify(Kind.COMMENT_ADDED, task, actor, _manager_ids(task) | {task.assignee_id})


# --- Sending (called by the Celery task) ------------------------------------


def _finish(notification: Notification, status: Status, reason: str = "") -> None:
    notification.status = status
    notification.reason = reason
    notification.finished_at = timezone.now()
    notification.save(update_fields=["status", "reason", "finished_at", "attempts"])


def _why_not(recipient: User, task: Task) -> str | None:
    if not recipient.is_active:
        return "recipient_inactive"
    if recipient.telegram_user_id is None:
        return "no_telegram"
    if task.deleted_at is not None:
        return "task_deleted"
    # The same check as opening the task in the CRM (D003, D020).
    if not policy.allowed(Actor.for_user(recipient), policy.READ, task):
        return "no_access"
    return None


def _message(notification: Notification, recipient: User, task: Task) -> TaskMessage:
    zone = ZoneInfo(settings.NOTIFICATION_TIME_ZONE)
    due = f"{task.due_at.astimezone(zone):%d.%m.%Y %H:%M %Z}" if task.due_at else None
    actor = notification.actor.display_name if notification.actor else None
    if notification.kind == Kind.TASK_ASSIGNED:
        text = texts.task_assigned(
            title=task.title,
            is_request=task.task_type == "request",
            department=task.responsible_department.name,
            due=due,
            actor=actor,
        )
    elif notification.kind == Kind.DEADLINE_CHANGED:
        text = texts.deadline_changed(title=task.title, due=due, actor=actor)
    else:
        text = texts.comment_added(title=task.title, actor=actor)
    # The assignee finds the task on their own board; a manager — among all tasks.
    view = "" if task.assignee_id == recipient.pk else "view=all&"
    return TaskMessage(
        chat_id=recipient.telegram_user_id or 0,
        text=text,
        url=f"{settings.WEB_PUBLIC_URL}/?{view}task={task.pk}",
    )


def deliver(notification_id: UUID) -> None:
    """Send one notification, once. Raises `TelegramUnavailableError` when a
    retry may help; every other outcome is recorded on the row."""
    retry = False
    with transaction.atomic():
        notification = (
            Notification.objects.select_for_update(of=("self",))
            .select_related("recipient", "actor", "task__responsible_department")
            .filter(pk=notification_id)
            .first()
        )
        # Sent, skipped or failed already (a repeated delivery of the job).
        if notification is None or notification.status != Status.PENDING:
            return
        recipient, task = notification.recipient, notification.task
        reason = _why_not(recipient, task)
        if reason is not None:
            _finish(notification, Status.SKIPPED, reason)
            return
        notification.attempts += 1
        try:
            get_gateway().send_task_message(_message(notification, recipient, task))
        except TelegramRefusedError:
            # Blocked the bot, never started it, or the bot is misconfigured.
            _finish(notification, Status.FAILED, "telegram_refused")
            return
        except TelegramUnavailableError:
            notification.save(update_fields=["attempts"])
            retry = True
        else:
            _finish(notification, Status.SENT)
    if retry:
        # Outside the transaction, so that the attempt count is kept.
        raise TelegramUnavailableError("temporary")


def give_up(notification_id: UUID) -> None:
    """No retries left: record the failure. The message is not sent later."""
    with transaction.atomic():
        notification = Notification.objects.select_for_update().filter(pk=notification_id).first()
        if notification is not None and notification.status == Status.PENDING:
            _finish(notification, Status.FAILED, "telegram_unavailable")
            logger.error("Notification %s could not be delivered", notification_id)
