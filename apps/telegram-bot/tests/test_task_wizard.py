"""`/task`: a manager gives a task to a particular employee from the bot (S6; D037)."""

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from crm.common.actors import Actor
from crm.conftest import EmployeeFactory
from crm.notifications.models import Notification
from crm.organization import services as org
from crm.tasks.models import Task
from crm.telegram import texts
from crm_bot.task_wizard import parse_due

from .telegram import SendMessage, callback_update, feed, message_update
from .test_request_wizard import Dialogue, name_of, publish, staff  # noqa: F401

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


def test_manager_gives_a_task_step_by_step(staff: dict[str, Any]) -> None:  # noqa: F811
    olga = Dialogue(staff["olga"])

    # One department: the bot starts with the assignee.
    assert olga.say("/task") == [texts.TASK_CHOOSE_ASSIGNEE]
    assert set(olga.buttons()) == {name_of(staff[name]) for name in ("anna", "boris", "olga")}
    assert olga.press(name_of(staff["anna"])) == [texts.TASK_TITLE]
    assert olga.say("  Подготовить   договор ") == [texts.TASK_DESCRIPTION]
    assert olga.say("С реквизитами клиента") == [texts.TASK_DUE]
    assert olga.say("завтра") == [texts.TASK_DUE_REFUSED]
    assert olga.say("15.12.2026 14:30") == [texts.TASK_PRIORITY]
    assert olga.buttons() == ["Низкий", "Обычный", "Высокий", "Срочный"]
    (summary,) = olga.press("Высокий")

    assert summary == (
        "Проверьте задачу.\n\n"
        "Название: Подготовить договор\n"
        "Отдел: Продажи\n"
        f"Исполнитель: {name_of(staff['anna'])}\n"
        "Срок: 15.12.2026 14:30 MSK\n"
        "Приоритет: Высокий\n\n"
        "С реквизитами клиента"
    )
    assert not Task.objects.exists()

    (done,) = olga.press(texts.BUTTON_CREATE_TASK)

    assert done == f"Задача «Подготовить договор» создана и назначена: {name_of(staff['anna'])}."
    task = Task.objects.get()
    assert (task.task_type, task.title, task.priority) == ("task", "Подготовить договор", "high")
    assert task.description == "С реквизитами клиента"
    assert task.author_id == staff["olga"].user.pk
    assert task.assignee_id == staff["anna"].user.pk
    assert task.due_at == datetime(2026, 12, 15, 11, 30, tzinfo=UTC)
    # The assignee is notified like for a task made on the website.
    assert Notification.objects.get().recipient_id == staff["anna"].user.pk


def test_short_way_without_description_and_deadline(staff: dict[str, Any]) -> None:  # noqa: F811
    olga = Dialogue(staff["olga"])
    olga.say("/task")
    olga.press(name_of(staff["boris"]))
    olga.say("Позвонить клиенту")
    assert olga.press(texts.BUTTON_SKIP) == [texts.TASK_DUE]
    assert olga.press(texts.BUTTON_NO_DUE) == [texts.TASK_PRIORITY]
    (summary,) = olga.press("Обычный")
    assert "Срок: без срока" in summary
    olga.press(texts.BUTTON_CREATE_TASK)

    task = Task.objects.get()
    assert (task.description, task.due_at, task.priority) == ("", None, "normal")


def test_department_is_asked_when_there_are_several(
    staff: dict[str, Any],  # noqa: F811
    admin_actor: Actor,
    make_employee: EmployeeFactory,
) -> None:
    support = org.create_department(actor=admin_actor, name="Поддержка")
    vera = make_employee("vera")
    org.add_member(actor=admin_actor, department_id=support.pk, user_id=vera.user.pk)
    org.add_manager(actor=admin_actor, department_id=support.pk, user_id=staff["olga"].user.pk)
    olga = Dialogue(staff["olga"])

    assert olga.say("/task") == [texts.TASK_CHOOSE_DEPARTMENT]
    assert olga.buttons() == ["Поддержка", "Продажи"]
    olga.press("Поддержка")
    assert name_of(vera) in olga.buttons()
    assert name_of(staff["anna"]) not in olga.buttons()
    olga.press(name_of(vera))
    olga.say("Ответить на обращение")
    olga.press(texts.BUTTON_SKIP)
    olga.press(texts.BUTTON_NO_DUE)
    olga.press("Срочный")
    olga.press(texts.BUTTON_CREATE_TASK)

    assert Task.objects.get().responsible_department_id == support.pk


def test_who_creates_no_tasks_gets_one_answer(staff: dict[str, Any]) -> None:  # noqa: F811
    # D037: an employee; and somebody the CRM does not know.
    assert Dialogue(staff["anna"]).say("/task") == [texts.TASK_NOT_ALLOWED]
    stranger = feed(message_update("/task", user_id=999_999))
    assert stranger.texts(SendMessage) == [texts.TASK_NOT_ALLOWED]
    group = feed(message_update("/task", user_id=staff["olga"].telegram_user_id, chat_type="group"))
    assert group.calls == []


def test_rights_lost_before_the_confirmation(staff: dict[str, Any], admin_actor: Actor) -> None:  # noqa: F811
    olga = Dialogue(staff["olga"])
    olga.say("/task")
    olga.press(name_of(staff["anna"]))
    olga.say("Задача")
    olga.press(texts.BUTTON_SKIP)
    olga.press(texts.BUTTON_NO_DUE)
    olga.press("Обычный")

    org.remove_manager(
        actor=admin_actor, department_id=staff["sales"].pk, user_id=staff["olga"].user.pk
    )

    assert olga.press(texts.BUTTON_CREATE_TASK) == [texts.TASK_REFUSED]
    assert not Task.objects.exists()


def test_double_tap_stale_buttons_and_cancel(staff: dict[str, Any], admin_actor: Actor) -> None:  # noqa: F811
    publish(admin_actor, [staff["sales"]], fields=[])
    olga = Dialogue(staff["olga"])
    olga.say("/task")
    stale = olga.data_of(name_of(staff["anna"]))
    olga.say("/task")  # a new dialogue
    assert olga.press_data(stale) == []
    nonce = olga.data_of(name_of(staff["anna"])).split(":")[1]
    assert olga.press_data(f"tk:{nonce}:create") == []  # not at the confirmation
    assert olga.press_data(f"tk:{nonce}:a:99") == []
    # A button of the other dialogue does nothing here.
    assert olga.press_data(f"rq:{nonce}:a:0") == []
    assert olga.say("текст вместо кнопки") == [texts.REQUEST_USE_BUTTONS]

    olga.press(name_of(staff["anna"]))
    assert olga.say("/cancel") == [texts.REQUEST_CANCELLED]
    assert olga.say("Название") == []

    olga.say("/task")
    olga.press(name_of(staff["anna"]))
    olga.say("Задача")
    olga.press(texts.BUTTON_SKIP)
    olga.press(texts.BUTTON_NO_DUE)
    olga.press("Обычный")
    create = olga.data_of(texts.BUTTON_CREATE_TASK)
    olga.press_data(create)
    again = feed(callback_update(create, user_id=olga.user_id), olga.storage)

    assert again.of(SendMessage) == []
    assert Task.objects.count() == 1


def test_deadline_forms() -> None:
    moscow = ZoneInfo("Europe/Moscow")

    assert parse_due("15.12.2026 14:30", moscow) == datetime(2026, 12, 15, 14, 30, tzinfo=moscow)
    # Only a date: the end of that day.
    assert parse_due(" 5.1.2027 ", moscow) == datetime(2027, 1, 5, 23, 59, tzinfo=moscow)
    for text in ("завтра", "31.02.2026", "15.12.2026 25:00", "2026-12-15", ""):
        assert parse_due(text, moscow) is None
