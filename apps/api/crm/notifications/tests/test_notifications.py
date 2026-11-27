"""Telegram notifications about tasks (S6; D012, D017, Q23): who is told, what
the message contains, and that rights are checked again when it is sent."""

from datetime import UTC, datetime
from typing import Any

import pytest
from celery.exceptions import Retry

from crm.access import services as access
from crm.access.permissions import Scope
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.identity import users
from crm.notifications import services, tasks
from crm.notifications.models import Kind, Notification, Status
from crm.organization import services as org
from crm.request_templates import services as templates
from crm.request_templates import submissions
from crm.tasks import services as task_services
from crm.tasks.models import Task
from crm.tasks.tests.test_tasks import World, make_task, uid, world  # noqa: F401
from crm.telegram.fake import FakeGateway
from crm.telegram.gateway import TelegramRefusedError, TelegramUnavailableError

pytestmark = pytest.mark.django_db

DUE = datetime(2026, 12, 15, 9, 0, tzinfo=UTC)


def outbox(**filters: Any) -> list[tuple[str, str, str]]:
    """(kind, recipient's login, status) of every row, oldest first."""
    rows = Notification.objects.filter(**filters).select_related("recipient")
    return sorted((row.kind, row.recipient.crm_login, row.status) for row in rows)


def send_all() -> None:
    for pk in Notification.objects.filter(status=Status.PENDING).values_list("pk", flat=True):
        services.deliver(pk)


def chat(actor: Actor) -> int:
    assert actor.user is not None
    assert actor.user.telegram_user_id is not None
    return actor.user.telegram_user_id


# --- Who is told ------------------------------------------------------------


def test_new_task_notifies_the_assignee_only(world: World) -> None:  # noqa: F811
    task = make_task(world)  # Olga creates for Anna

    assert outbox() == [("task_assigned", "anna", "pending")]
    send_all()

    (message,) = FakeGateway.messages
    assert message.chat_id == chat(world.anna)
    assert world.olga.user is not None
    assert message.text == (
        "Вам назначена задача «Подготовить коммерческое предложение».\n\n"
        f"Отдел: Продажи\nСрок: не указан\nНазначил(а): {world.olga.user.display_name}"
    )
    assert message.url.endswith(f"/?task={task.pk}")
    assert outbox() == [("task_assigned", "anna", "sent")]


def test_nobody_is_told_about_their_own_action(world: World) -> None:  # noqa: F811
    make_task(world, assignee=world.olga)  # the manager takes the task herself

    assert outbox() == []


def test_request_by_template_notifies_as_a_request(world: World) -> None:  # noqa: F811
    template = templates.create_template(actor=world.admin, name="Счёт")
    templates.set_departments(
        actor=world.admin, template_id=template.pk, department_ids=[world.sales.pk]
    )
    templates.publish(actor=world.admin, template_id=template.pk)

    submissions.submit(
        actor=world.olga,
        template_id=template.pk,
        version=1,
        department_id=world.sales.pk,
        assignee_id=uid(world.anna),
        title="Счёт для «Ромашки»",
        form_values={},
        due_at=DUE,
    )
    send_all()

    (message,) = FakeGateway.messages
    assert message.text.startswith("Вам назначена заявка «Счёт для «Ромашки»».")
    # Shown in the configured zone (Moscow by default), not in UTC.
    assert "Срок: 15.12.2026 12:00 MSK" in message.text


def test_reassignment_notifies_the_new_assignee(world: World) -> None:  # noqa: F811
    task = make_task(world)
    Notification.objects.all().delete()

    task_services.reassign(actor=world.olga, task_id=task.pk, assignee_id=uid(world.boris))

    assert outbox() == [("task_assigned", "boris", "pending")]


def test_assignee_moving_the_deadline_notifies_the_managers(world: World) -> None:  # noqa: F811
    # D017. A second manager of Sales is told as well.
    org.add_manager(actor=world.admin, department_id=world.sales.pk, user_id=uid(world.pavel))
    task = make_task(world)
    Notification.objects.all().delete()

    task_services.change_deadline(actor=world.anna, task_id=task.pk, due_at=DUE)
    task_services.change_deadline(actor=world.anna, task_id=task.pk, due_at=DUE)  # no change

    assert outbox() == [
        ("deadline_changed", "olga", "pending"),
        ("deadline_changed", "pavel", "pending"),
    ]
    send_all()
    texts = {message.chat_id: message for message in FakeGateway.messages}
    olga = texts[chat(world.olga)]
    assert "изменил(а) срок задачи «Подготовить коммерческое предложение»" in olga.text
    assert "Новый срок: 15.12.2026 12:00 MSK" in olga.text
    assert olga.url.endswith(f"/?view=all&task={task.pk}")


def test_manager_moving_the_deadline_notifies_the_assignee(world: World) -> None:  # noqa: F811
    task = make_task(world)
    Notification.objects.all().delete()

    task_services.change_deadline(actor=world.olga, task_id=task.pk, due_at=DUE)

    assert outbox() == [("deadline_changed", "anna", "pending")]


def test_comment_notifies_the_other_side_without_its_text(world: World) -> None:  # noqa: F811
    task = make_task(world)
    Notification.objects.all().delete()

    task_services.add_comment(actor=world.anna, task_id=task.pk, body="Секретная сумма 5 млн")
    task_services.add_comment(actor=world.olga, task_id=task.pk, body="Принято")

    assert outbox() == [
        ("comment_added", "anna", "pending"),
        ("comment_added", "olga", "pending"),
    ]
    send_all()
    for message in FakeGateway.messages:
        assert message.text.startswith("Новый комментарий от ")
        assert "Секретная" not in message.text
        assert "Принято" not in message.text


def test_hand_over_on_deactivation_notifies_the_manager(world: World) -> None:  # noqa: F811
    org.add_manager(
        actor=world.admin, department_id=world.sales.pk, user_id=uid(world.olga), designated=True
    )
    make_task(world)
    Notification.objects.all().delete()
    assert world.anna.user is not None

    users.deactivate_user(actor=world.admin, user=world.anna.user)

    assert outbox() == [("task_assigned", "olga", "pending")]


def test_rolled_back_change_notifies_nobody(world: World) -> None:  # noqa: F811
    from django.db import transaction

    class AbortError(Exception):
        pass

    def attempt() -> None:
        with transaction.atomic():
            make_task(world)
            raise AbortError

    with pytest.raises(AbortError):
        attempt()

    assert not Task.objects.exists()
    assert outbox() == []


# --- Rights at the moment of sending (Q23) ----------------------------------


def test_manager_who_lost_the_department_is_not_told(world: World) -> None:  # noqa: F811
    org.add_manager(actor=world.admin, department_id=world.sales.pk, user_id=uid(world.pavel))
    task = make_task(world)
    Notification.objects.all().delete()
    task_services.add_comment(actor=world.anna, task_id=task.pk, body="Готово")

    org.remove_manager(actor=world.admin, department_id=world.sales.pk, user_id=uid(world.pavel))
    send_all()

    assert [message.chat_id for message in FakeGateway.messages] == [chat(world.olga)]
    skipped = Notification.objects.get(recipient_id=uid(world.pavel))
    assert (skipped.status, skipped.reason, skipped.attempts) == ("skipped", "no_access", 0)
    assert skipped.finished_at is not None


def test_former_assignee_is_not_told(world: World) -> None:  # noqa: F811
    task = make_task(world)  # a pending "assigned" for Anna
    task_services.reassign(actor=world.olga, task_id=task.pk, assignee_id=uid(world.boris))

    send_all()

    assert [message.chat_id for message in FakeGateway.messages] == [chat(world.boris)]
    assert outbox(recipient_id=uid(world.anna)) == [("task_assigned", "anna", "skipped")]


@pytest.mark.parametrize(
    ("change", "reason"),
    [("deactivate", "recipient_inactive"), ("unbind", "no_telegram"), ("trash", "task_deleted")],
)
def test_other_reasons_to_skip(world: World, change: str, reason: str) -> None:  # noqa: F811
    task = make_task(world, assignee=world.boris)
    assert world.boris.user is not None
    if change == "deactivate":
        org.add_manager(
            actor=world.admin,
            department_id=world.sales.pk,
            user_id=uid(world.olga),
            designated=True,
        )
        users.deactivate_user(actor=world.admin, user=world.boris.user)
    elif change == "unbind":
        type(world.boris.user).objects.filter(pk=uid(world.boris)).update(
            telegram_user_id=None, telegram_bound_at=None
        )
    else:
        task_services.trash_task(actor=world.olga, task_id=task.pk)

    send_all()

    assert chat(world.boris) not in [message.chat_id for message in FakeGateway.messages]
    row = Notification.objects.get(recipient_id=uid(world.boris), kind=Kind.TASK_ASSIGNED)
    assert (row.status, row.reason) == ("skipped", reason)


def test_superuser_and_administrator_get_nothing(world: World) -> None:  # noqa: F811
    task = make_task(world)
    task_services.add_comment(actor=world.anna, task_id=task.pk, body="Готово")
    task_services.change_deadline(actor=world.anna, task_id=task.pk, due_at=DUE)

    recipients = set(Notification.objects.values_list("recipient__crm_login", flat=True))

    assert recipients == {"anna", "olga"}
    # Zoya reads every task (Q29) and still is not told about them.
    assert access.has_permission(world.zoya, "task.read", at_least=Scope.COMPANY)


# --- Delivery ---------------------------------------------------------------


def test_delivery_is_not_repeated(world: World) -> None:  # noqa: F811
    make_task(world)
    (row,) = Notification.objects.all()

    services.deliver(row.pk)
    services.deliver(row.pk)
    tasks.deliver_notification.apply(args=(str(row.pk),)).get()

    assert len(FakeGateway.messages) == 1
    row.refresh_from_db()
    assert (row.status, row.attempts) == ("sent", 1)


def test_refusal_by_telegram_is_final(world: World) -> None:  # noqa: F811
    make_task(world)
    (row,) = Notification.objects.all()
    FakeGateway.failure = TelegramRefusedError("TelegramForbiddenError")

    tasks.deliver_notification.apply(args=(str(row.pk),)).get()

    row.refresh_from_db()
    assert (row.status, row.reason, row.attempts) == ("failed", "telegram_refused", 1)


def test_temporary_failure_is_retried_then_given_up(world: World) -> None:  # noqa: F811
    make_task(world)
    (row,) = Notification.objects.all()
    FakeGateway.failure = TelegramUnavailableError("TimeoutError")

    with pytest.raises(Retry):
        tasks.deliver_notification.apply(args=(str(row.pk),), throw=True).get()
    row.refresh_from_db()
    assert (row.status, row.attempts) == ("pending", 1)

    tasks.deliver_notification.apply(args=(str(row.pk),), retries=tasks.MAX_RETRIES).get()
    row.refresh_from_db()
    assert (row.status, row.reason, row.attempts) == ("failed", "telegram_unavailable", 2)

    # Telegram is back, but a message that was given up on is not sent late.
    FakeGateway.failure = None
    services.deliver(row.pk)
    assert FakeGateway.messages == []


def test_change_succeeds_and_is_sent_after_commit(
    world: World,  # noqa: F811
    django_capture_on_commit_callbacks: Any,
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        make_task(world)

    assert len(FakeGateway.messages) == 1
    assert outbox() == [("task_assigned", "anna", "sent")]


def test_telegram_being_down_does_not_fail_the_change(
    world: World,  # noqa: F811
    django_capture_on_commit_callbacks: Any,
) -> None:
    FakeGateway.failure = TelegramRefusedError("TelegramForbiddenError")

    with django_capture_on_commit_callbacks(execute=True):
        task = make_task(world)

    assert Task.objects.filter(pk=task.pk).exists()
    assert outbox() == [("task_assigned", "anna", "failed")]


def test_nothing_about_messages_is_stored_or_audited(world: World) -> None:  # noqa: F811
    task = make_task(world)
    task_services.add_comment(actor=world.anna, task_id=task.pk, body="Секрет")
    send_all()

    stored = [field.name for field in Notification._meta.get_fields()]
    assert "text" not in stored
    assert "body" not in stored
    assert not AuditEvent.objects.filter(action__startswith="notification").exists()


# --- Status -----------------------------------------------------------------


def status_named(name: str) -> Any:
    from crm.tasks.models import TaskStatus

    return TaskStatus.objects.get(name=name)


def test_status_change_notifies_the_other_side(world: World) -> None:  # noqa: F811
    task = make_task(world)
    Notification.objects.all().delete()

    task_services.change_status(
        actor=world.anna, task_id=task.pk, status_id=status_named("В работе").pk
    )
    task_services.change_status(
        actor=world.anna, task_id=task.pk, status_id=status_named("В работе").pk
    )  # the same status again: nothing new

    assert outbox() == [("status_changed", "olga", "pending")]
    send_all()
    (message,) = FakeGateway.messages
    assert message.text.endswith(
        "перевёл(а) задачу «Подготовить коммерческое предложение» в статус «В работе»."
    )
    assert message.url.endswith(f"/?view=all&task={task.pk}")


def test_completion_is_announced(world: World) -> None:  # noqa: F811
    task = make_task(world)
    task_services.change_status(
        actor=world.anna, task_id=task.pk, status_id=status_named("В работе").pk
    )
    Notification.objects.all().delete()

    task_services.change_status(
        actor=world.anna, task_id=task.pk, status_id=status_named("Готово").pk
    )
    send_all()

    (message,) = FakeGateway.messages
    assert message.chat_id == chat(world.olga)
    assert message.text.endswith("завершил(а) задачу «Подготовить коммерческое предложение».")
    # D041: the completed task is still on the board.
    assert message.url.endswith(f"/?view=all&task={task.pk}")


def test_manager_changing_the_status_notifies_the_assignee(world: World) -> None:  # noqa: F811
    task = make_task(world)
    Notification.objects.all().delete()

    task_services.change_status(
        actor=world.olga, task_id=task.pk, status_id=status_named("В работе").pk
    )

    assert outbox() == [("status_changed", "anna", "pending")]


# --- Project invitations (Q10) ----------------------------------------------


def invite_vera(world: World) -> Any:  # noqa: F811
    """Olga (Sales) asks to bring Vera (Support, managed by Pavel) into her project."""
    from crm.projects import services as projects

    project = projects.create_project(
        actor=world.olga, name="Запуск продукта", department_id=world.sales.pk
    )
    joined = projects.add_participant(
        actor=world.olga,
        project_id=project.pk,
        user_id=uid(world.vera),
        department_id=world.support.pk,
    )
    assert joined.invitation is not None
    return joined.invitation


def test_invitation_asks_the_employees_manager(world: World) -> None:  # noqa: F811
    invite_vera(world)

    assert outbox() == [("invitation_requested", "pavel", "pending")]
    send_all()
    (message,) = FakeGateway.messages
    assert message.chat_id == chat(world.pavel)
    assert "просит включить сотрудника в проект «Запуск продукта»" in message.text
    assert "Отдел: Поддержка" in message.text
    assert message.url.endswith("/projects")


def test_decision_is_told_to_the_requester_and_the_employee(world: World) -> None:  # noqa: F811
    from crm.projects import services as projects

    invitation = invite_vera(world)
    Notification.objects.all().delete()

    projects.approve_invitation(actor=world.pavel, invitation_id=invitation.pk)

    assert outbox() == [
        ("invitation_decided", "olga", "pending"),
        ("project_joined", "vera", "pending"),
    ]
    send_all()
    by_chat = {message.chat_id: message.text for message in FakeGateway.messages}
    assert "в проекте «Запуск продукта» одобрено" in by_chat[chat(world.olga)]
    assert by_chat[chat(world.vera)] == "Вас включили в проект «Запуск продукта»."


def test_declined_invitation_tells_only_the_requester(world: World) -> None:  # noqa: F811
    from crm.projects import services as projects

    invitation = invite_vera(world)
    Notification.objects.all().delete()

    projects.decline_invitation(actor=world.pavel, invitation_id=invitation.pk, reason="Занята")
    send_all()

    (message,) = FakeGateway.messages
    assert message.chat_id == chat(world.olga)
    assert "отклонено" in message.text
    # The reason typed by the manager is not sent.
    assert "Занята" not in message.text


def test_invitation_rights_are_checked_when_sending(world: World) -> None:  # noqa: F811
    from crm.projects import services as projects

    # Already decided before the request went out.
    invitation = invite_vera(world)
    projects.approve_invitation(actor=world.pavel, invitation_id=invitation.pk)
    send_all()
    request_row = Notification.objects.get(kind=Kind.INVITATION_REQUESTED)
    assert (request_row.status, request_row.reason) == ("skipped", "already_decided")

    # The requester stopped managing the project's department; the employee was removed.
    FakeGateway.clear()
    Notification.objects.all().delete()
    invitation.refresh_from_db()
    services.invitation_decided(invitation=invitation, actor=world.pavel)
    org.add_manager(
        actor=world.admin, department_id=world.sales.pk, user_id=uid(world.boris), designated=True
    )
    org.remove_manager(actor=world.admin, department_id=world.sales.pk, user_id=uid(world.olga))
    projects.remove_participant(
        actor=world.boris, project_id=invitation.project_id, user_id=uid(world.vera)
    )
    send_all()

    assert FakeGateway.messages == []
    assert outbox() == [
        ("invitation_decided", "olga", "skipped"),
        ("project_joined", "vera", "skipped"),
    ]


def test_manager_who_lost_the_department_is_not_asked(world: World) -> None:  # noqa: F811
    org.add_manager(actor=world.admin, department_id=world.support.pk, user_id=uid(world.boris))
    invite_vera(world)
    org.remove_manager(actor=world.admin, department_id=world.support.pk, user_id=uid(world.boris))

    send_all()

    assert [message.chat_id for message in FakeGateway.messages] == [chat(world.pavel)]
    row = Notification.objects.get(recipient_id=uid(world.boris))
    assert (row.status, row.reason) == ("skipped", "no_access")
