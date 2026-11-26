"""`/request`: the dialogue that makes a request by a template (S6; D040, Q21)."""

import json
from collections.abc import Mapping
from typing import Any

import pytest
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.conftest import Employee, EmployeeFactory
from crm.files.tests import samples
from crm.identity import users
from crm.organization import services as org
from crm.organization.models import Department
from crm.request_templates import services as templates
from crm.request_templates.models import RequestTemplate, Submission
from crm.tasks.models import Attachment, Task
from crm.telegram import texts

from .telegram import (
    EditMessageReplyMarkup,
    RecordingSession,
    SendMessage,
    callback_update,
    document_update,
    feed,
    message_update,
)

pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

FIELDS: list[dict[str, Any]] = [
    {"key": "client", "type": "text", "label": "Клиент", "required": True},
    {"key": "amount", "type": "number", "label": "Сумма", "currency": "RUB", "min": 0},
    {"key": "pay_by", "type": "date", "label": "Срок оплаты"},
    {"key": "kind", "type": "select", "label": "Вид", "options": ["Счёт", "Акт"], "required": True},
    {
        "key": "tags",
        "type": "select",
        "label": "Метки",
        "options": ["Новый", "VIP"],
        "multiple": True,
    },
    {"key": "owner", "type": "employee", "label": "Куратор"},
    {"key": "scan", "type": "file", "label": "Скан"},
    {"key": "urgent", "type": "boolean", "label": "Срочно"},
]


class JsonStorage(MemoryStorage):
    """Keeps the data the way the Redis storage of the real process does: as
    JSON, so tuples come back as lists and only plain values survive."""

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        await super().set_data(key, json.loads(json.dumps(data)))


HINTS = {
    texts.REQUEST_USE_BUTTONS,
    texts.REQUEST_SEND_FILE,
    texts.REQUEST_FILE_REFUSED,
    texts.REQUEST_FILE_TOO_LARGE,
}


class Dialogue:
    """One person talking to the bot; remembers the last keyboard."""

    def __init__(self, employee: Employee) -> None:
        self.user_id = employee.telegram_user_id
        self.storage = JsonStorage()
        self.keyboard: Any = None
        self.replies: list[str] = []

    def _after(self, session: RecordingSession) -> list[str]:
        sent = session.of(SendMessage)
        for message in sent:
            # A hint without buttons leaves the earlier question's buttons in place.
            if message.reply_markup is not None or message.text not in HINTS:
                self.keyboard = message.reply_markup
        for edit in session.of(EditMessageReplyMarkup):
            if edit.reply_markup is not None:
                self.keyboard = edit.reply_markup
        self.replies = [str(message.text) for message in sent]
        return self.replies

    def say(self, text: str) -> list[str]:
        return self._after(feed(message_update(text, user_id=self.user_id), self.storage))

    def buttons(self) -> list[str]:
        if self.keyboard is None:
            return []
        return [button.text for row in self.keyboard.inline_keyboard for button in row]

    def data_of(self, label: str) -> str:
        for row in self.keyboard.inline_keyboard:
            for button in row:
                if button.text == label:
                    return str(button.callback_data)
        raise AssertionError(f"No button {label!r} among {self.buttons()}")

    def press(self, label: str) -> list[str]:
        return self.press_data(self.data_of(label))

    def press_data(self, data: str) -> list[str]:
        return self._after(feed(callback_update(data, user_id=self.user_id), self.storage))

    def send_file(self, name: str, content: bytes, size: int | None = None) -> list[str]:
        update = document_update(name, content, user_id=self.user_id, size=size)
        return self._after(feed(update, self.storage))


@pytest.fixture
def staff(admin_actor: Actor, make_employee: EmployeeFactory) -> dict[str, Any]:
    sales = org.create_department(actor=admin_actor, name="Продажи")
    people = {name: make_employee(name) for name in ("olga", "anna", "boris")}
    for employee in people.values():
        org.add_member(actor=admin_actor, department_id=sales.pk, user_id=employee.user.pk)
    org.add_manager(actor=admin_actor, department_id=sales.pk, user_id=people["olga"].user.pk)
    return {"sales": sales, **people}


def publish(
    admin_actor: Actor,
    departments: list[Department],
    name: str = "Счёт клиенту",
    fields: list[dict[str, Any]] | None = None,
) -> RequestTemplate:
    template = templates.create_template(actor=admin_actor, name=name)
    templates.update_template(
        actor=admin_actor,
        template_id=template.pk,
        fields=FIELDS if fields is None else fields,
        checkpoints=["Проверить реквизиты"],
    )
    templates.set_departments(
        actor=admin_actor, template_id=template.pk, department_ids=[d.pk for d in departments]
    )
    templates.publish(actor=admin_actor, template_id=template.pk)
    return template


def name_of(employee: Employee) -> str:
    return employee.user.display_name


def to_first_question(olga: Dialogue, assignee: Employee) -> None:
    olga.say("/request")
    olga.press(name_of(assignee))
    olga.press(texts.button_keep_title("Счёт клиенту"))


# --- The whole way ----------------------------------------------------------


def test_manager_makes_a_request_step_by_step(staff: dict[str, Any], admin_actor: Actor) -> None:
    publish(admin_actor, [staff["sales"]])
    olga = Dialogue(staff["olga"])

    # One form and one department: the bot goes straight to the assignee.
    assert olga.say("/request") == [texts.REQUEST_CHOOSE_ASSIGNEE]
    # Employees and the manager herself (D037).
    assert set(olga.buttons()) == {name_of(staff[name]) for name in ("anna", "boris", "olga")}
    (title_question,) = olga.press(name_of(staff["anna"]))
    assert "Название заявки?" in title_question
    (question,) = olga.say("Счёт для «Ромашки»")
    assert question.startswith("1 из 8. Клиент")

    (question,) = olga.say("ООО Ромашка")
    assert question.startswith("2 из 8. Сумма (необязательно)")
    assert "RUB" in question
    (question,) = olga.say("150000,50")
    assert "Введите дату, например 15.12.2026." in question
    (question,) = olga.say("15.12.2026")
    assert olga.buttons() == ["Счёт", "Акт"]  # required: nothing to skip
    (question,) = olga.press("Акт")
    assert olga.buttons() == ["Новый", "VIP", texts.BUTTON_DONE, texts.BUTTON_SKIP]
    assert olga.press("VIP") == []
    assert olga.buttons()[:2] == ["Новый", "✓ VIP"]
    (question,) = olga.press(texts.BUTTON_DONE)
    assert question.startswith("6 из 8. Куратор")
    (question,) = olga.press(name_of(staff["boris"]))
    assert "Отправьте файл" in question
    (question,) = olga.send_file("Договор.pdf", samples.PDF)
    assert question.startswith("8 из 8. Срочно")
    (summary,) = olga.press(texts.BUTTON_YES)

    assert summary == (
        "Проверьте заявку.\n\n"
        "Шаблон: Счёт клиенту\n"
        "Название: Счёт для «Ромашки»\n"
        "Отдел: Продажи\n"
        f"Исполнитель: {name_of(staff['anna'])}\n\n"
        "Клиент: ООО Ромашка\n"
        "Сумма: 150000,50 RUB\n"
        "Срок оплаты: 15.12.2026\n"
        "Вид: Акт\n"
        "Метки: VIP\n"
        f"Куратор: {name_of(staff['boris'])}\n"
        "Скан: Договор.pdf\n"
        "Срочно: Да"
    )
    assert not Task.objects.exists()  # nothing is created before the confirmation

    (done,) = olga.press(texts.BUTTON_SUBMIT)

    assert done == f"Заявка «Счёт для «Ромашки»» создана и назначена: {name_of(staff['anna'])}."
    task = Task.objects.get()
    assert (task.task_type, task.title) == ("request", "Счёт для «Ромашки»")
    assert task.author_id == staff["olga"].user.pk
    assert task.assignee_id == staff["anna"].user.pk
    assert task.checkpoints.count() == 1
    submission = Submission.objects.get(task=task)
    assert submission.source == "telegram"
    attachment = Attachment.objects.get(task=task)
    assert attachment.original_name == "Договор.pdf"
    assert submission.values == {
        "client": "ООО Ромашка",
        "amount": "150000.50",
        "pay_by": "2026-12-15",
        "kind": "Акт",
        "tags": ["VIP"],
        "owner": str(staff["boris"].user.pk),
        "urgent": True,
        "scan": str(attachment.pk),
    }
    # Typed answers are in the request and nowhere in the audit log.
    logged = str(list(AuditEvent.objects.values_list("metadata", flat=True)))
    assert "Ромашка" not in logged


def test_optional_questions_can_be_skipped(staff: dict[str, Any], admin_actor: Actor) -> None:
    publish(admin_actor, [staff["sales"]])
    olga = Dialogue(staff["olga"])
    to_first_question(olga, staff["anna"])

    olga.say("Ромашка")
    for _ in ("amount", "pay_by"):
        olga.press(texts.BUTTON_SKIP)
    olga.press("Счёт")
    for _ in ("tags", "owner", "scan"):
        olga.press(texts.BUTTON_SKIP)
    (summary,) = olga.press(texts.BUTTON_SKIP)
    assert summary.endswith("Клиент: Ромашка\nВид: Счёт")
    olga.press(texts.BUTTON_SUBMIT)

    assert Submission.objects.get().values == {"client": "Ромашка", "kind": "Счёт"}
    assert Task.objects.get().title == "Счёт клиенту"


def test_choosing_among_forms_and_departments(
    staff: dict[str, Any], admin_actor: Actor, make_employee: EmployeeFactory
) -> None:
    support = org.create_department(actor=admin_actor, name="Поддержка")
    vera = make_employee("vera")
    org.add_member(actor=admin_actor, department_id=support.pk, user_id=vera.user.pk)
    org.add_manager(actor=admin_actor, department_id=support.pk, user_id=staff["olga"].user.pk)
    publish(admin_actor, [staff["sales"], support], fields=[])
    publish(admin_actor, [staff["sales"]], name="Отпуск", fields=[])
    olga = Dialogue(staff["olga"])

    assert olga.say("/request") == [texts.REQUEST_CHOOSE_FORM]
    assert olga.buttons() == ["Отпуск", "Счёт клиенту"]
    assert olga.press("Счёт клиенту") == [texts.REQUEST_CHOOSE_DEPARTMENT]
    assert olga.buttons() == ["Поддержка", "Продажи"]
    assert olga.press("Поддержка") == [texts.REQUEST_CHOOSE_ASSIGNEE]
    # Only people of the chosen department.
    assert name_of(vera) in olga.buttons()
    assert name_of(staff["anna"]) not in olga.buttons()
    olga.press(name_of(vera))
    (summary,) = olga.press(texts.button_keep_title("Счёт клиенту"))  # a form without fields
    assert "Отдел: Поддержка" in summary
    olga.press(texts.BUTTON_SUBMIT)

    assert Task.objects.get().responsible_department_id == support.pk


# --- Who may (D040) ---------------------------------------------------------


def test_employee_is_offered_nothing(staff: dict[str, Any], admin_actor: Actor) -> None:
    publish(admin_actor, [staff["sales"]])

    assert Dialogue(staff["anna"]).say("/request") == [texts.REQUEST_NO_FORMS]


def test_stranger_and_deactivated_account_are_refused(
    staff: dict[str, Any], admin_actor: Actor
) -> None:
    publish(admin_actor, [staff["sales"]])
    stranger = feed(message_update("/request", user_id=999_999))
    assert stranger.texts(SendMessage) == [texts.REQUEST_NOT_LINKED]

    olga = Dialogue(staff["olga"])
    to_first_question(olga, staff["anna"])
    org.add_manager(
        actor=admin_actor,
        department_id=staff["sales"].pk,
        user_id=staff["boris"].user.pk,
        designated=True,
    )
    users.deactivate_user(actor=admin_actor, user=staff["olga"].user)

    # The account was closed in the middle of the dialogue.
    olga.say("Ромашка")
    olga.press(texts.BUTTON_SKIP)
    olga.press(texts.BUTTON_SKIP)
    olga.press("Счёт")
    for _ in range(4):
        olga.press(texts.BUTTON_SKIP)
    assert olga.press(texts.BUTTON_SUBMIT) == [texts.REQUEST_NOT_LINKED]
    assert not Task.objects.exists()


def test_group_chat_is_ignored(staff: dict[str, Any], admin_actor: Actor) -> None:
    publish(admin_actor, [staff["sales"]])

    session = feed(
        message_update("/request", user_id=staff["olga"].telegram_user_id, chat_type="group")
    )

    assert session.calls == []


def test_rights_lost_before_the_confirmation(staff: dict[str, Any], admin_actor: Actor) -> None:
    template = publish(admin_actor, [staff["sales"]], fields=[])
    olga = Dialogue(staff["olga"])
    olga.say("/request")
    olga.press(name_of(staff["anna"]))
    olga.press(texts.button_keep_title("Счёт клиенту"))

    templates.set_active(actor=admin_actor, template_id=template.pk, active=False)

    assert olga.press(texts.BUTTON_SUBMIT) == [texts.REQUEST_TEMPLATE_CHANGED]
    assert not Task.objects.exists()


# --- Answers ----------------------------------------------------------------


def test_bad_answers_are_asked_again(staff: dict[str, Any], admin_actor: Actor) -> None:
    publish(admin_actor, [staff["sales"]])
    olga = Dialogue(staff["olga"])
    to_first_question(olga, staff["anna"])
    olga.say("Ромашка")

    assert olga.say("много") == [texts.request_refusal("invalid")]
    assert olga.say("-5") == [texts.request_refusal("out_of_range")]
    olga.say("100")
    assert olga.say("завтра") == [texts.request_refusal("invalid")]
    assert olga.say("31.02.2026") == [texts.request_refusal("invalid")]
    olga.say("15.12.2026")
    # Typing where a button is expected.
    assert olga.say("Счёт") == [texts.REQUEST_USE_BUTTONS]
    (question,) = olga.press("Счёт")
    assert question.startswith("5 из 8. Метки")


def test_files_are_checked_when_sent(staff: dict[str, Any], admin_actor: Actor) -> None:
    publish(
        admin_actor,
        [staff["sales"]],
        fields=[{"key": "scan", "type": "file", "label": "Скан", "required": True}],
    )
    olga = Dialogue(staff["olga"])
    to_first_question(olga, staff["anna"])

    assert olga.buttons() == []  # required: no skipping
    assert olga.say("вот файл") == [texts.REQUEST_SEND_FILE]
    assert olga.send_file("big.pdf", samples.PDF, size=21 * 1024 * 1024) == [
        texts.REQUEST_FILE_TOO_LARGE
    ]
    assert olga.send_file("virus.pdf", b"MZ\x90\x00 program") == [texts.REQUEST_FILE_REFUSED]
    (summary,) = olga.send_file("Скан.pdf", samples.PDF)
    assert summary.endswith("Скан: Скан.pdf")


# --- Buttons that are no longer valid ---------------------------------------


def test_double_tap_creates_one_request(staff: dict[str, Any], admin_actor: Actor) -> None:
    publish(admin_actor, [staff["sales"]], fields=[])
    olga = Dialogue(staff["olga"])
    olga.say("/request")
    olga.press(name_of(staff["anna"]))
    olga.press(texts.button_keep_title("Счёт клиенту"))
    submit = olga.data_of(texts.BUTTON_SUBMIT)

    olga.press_data(submit)
    again = feed(callback_update(submit, user_id=olga.user_id), olga.storage)

    assert Task.objects.count() == 1
    assert again.of(SendMessage) == []


def test_old_and_foreign_buttons_do_nothing(staff: dict[str, Any], admin_actor: Actor) -> None:
    publish(admin_actor, [staff["sales"]], fields=[])
    olga = Dialogue(staff["olga"])
    olga.say("/request")
    stale = olga.data_of(name_of(staff["anna"]))
    olga.say("/request")  # a new dialogue: the earlier buttons are dead

    assert olga.press_data(stale) == []
    assert olga.press_data("rq:zzzzzz:submit") == []
    assert olga.press_data("rq:broken") == []
    # Out-of-range and non-numeric choices.
    nonce = olga.data_of(name_of(staff["anna"])).split(":")[1]
    assert olga.press_data(f"rq:{nonce}:a:99") == []
    assert olga.press_data(f"rq:{nonce}:a:x") == []
    assert olga.press_data(f"rq:{nonce}:submit") == []  # not at the confirmation yet
    assert not Task.objects.exists()


def test_cancel(staff: dict[str, Any], admin_actor: Actor) -> None:
    publish(admin_actor, [staff["sales"]])
    olga = Dialogue(staff["olga"])

    assert olga.say("/cancel") == [texts.REQUEST_NOTHING_TO_CANCEL]
    to_first_question(olga, staff["anna"])
    assert olga.say("/cancel") == [texts.REQUEST_CANCELLED]
    # The dialogue is over: text is not taken as an answer any more.
    assert olga.say("Ромашка") == []
    assert not Task.objects.exists()
