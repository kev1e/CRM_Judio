"""`/task`: a manager gives a task to a particular employee from a private chat
(S6; D037).

Like the request dialogue it only collects answers: who may create tasks, for
which departments and for whom is decided by `crm.tasks.services`, and
`create_task` checks everything again. The sender is identified on every step
from the numeric Telegram ID of the update.

PROVISIONAL (docs/OPEN_QUESTIONS.md): a date without a time means the end of
that day; times are understood in `NOTIFICATION_TIME_ZONE`.
"""

import secrets
from contextlib import suppress
from datetime import datetime, time
from functools import partial
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from django.conf import settings

from crm.common.exceptions import DomainError
from crm.request_templates import values
from crm.tasks import services as tasks
from crm.telegram import gateway, texts
from crm_bot import domain
from crm_bot.request_wizard import _actor, _choices, _index, _keyboard, _stop

PREFIX = "tk"
MAX_DESCRIPTION = 4000  # a Telegram message is not longer anyway


class TaskWizard(StatesGroup):
    department = State()
    assignee = State()
    title = State()
    description = State()
    due = State()
    priority = State()
    confirm = State()


def _buttons(nonce: str, rows: list[list[tuple[str, str]]]) -> Any:
    return _keyboard(nonce, rows, prefix=PREFIX)


def parse_due(text: str, zone: ZoneInfo) -> datetime | None:
    """`15.12.2026 14:30`, or `15.12.2026` for the end of that day."""
    with_time = values.date_from_text({"with_time": True}, text, zone)
    if with_time != text:
        return datetime.fromisoformat(with_time)
    only_date = values.date_from_text({"with_time": False}, text, zone)
    if only_date != text:
        day = datetime.fromisoformat(only_date).date()
        return datetime.combine(day, time(23, 59), tzinfo=zone)
    return None


def _shown_due(data: dict[str, Any]) -> str | None:
    if not data.get("due_at"):
        return None
    zone = ZoneInfo(settings.NOTIFICATION_TIME_ZONE)
    return f"{datetime.fromisoformat(data['due_at']).astimezone(zone):%d.%m.%Y %H:%M %Z}"


# --- Asking -----------------------------------------------------------------


async def begin(message: Message, state: FSMContext) -> None:
    sender = message.from_user
    if sender is None or sender.is_bot or message.chat.type != ChatType.PRIVATE:
        return
    await state.clear()
    actor = await domain.call(partial(_actor, sender.id))
    departments: list[tuple[str, str]] = []
    if actor is not None:
        with suppress(DomainError):
            departments = await domain.call(
                lambda: [(str(d.pk), d.name) for d in tasks.assignable_departments(actor)]
            )
    if not departments:
        # The same answer to a stranger, an employee and anybody else who creates no tasks.
        await message.answer(texts.TASK_NOT_ALLOWED)
        return
    nonce = secrets.token_hex(3)
    data = {
        "nonce": nonce,
        "telegram_user_id": sender.id,
        "departments": departments,
        "description": "",
        "due_at": None,
        "priority": "normal",
    }
    await state.set_data(data)
    if len(departments) == 1:
        await _set_department(message, state, data, 0)
        return
    await state.set_state(TaskWizard.department)
    await message.answer(
        texts.TASK_CHOOSE_DEPARTMENT,
        reply_markup=_choices(nonce, "d", [name for _, name in departments], prefix=PREFIX),
    )


async def _set_department(
    target: Message, state: FSMContext, data: dict[str, Any], index: int
) -> None:
    department_id, department_name = data["departments"][index]
    actor = await domain.call(partial(_actor, data["telegram_user_id"]))
    people: list[tuple[str, str]] = []
    if actor is not None:
        with suppress(DomainError):
            people = await domain.call(
                lambda: [
                    (str(person.pk), person.display_name)
                    for person in tasks.eligible_assignees(actor, UUID(department_id))
                ]
            )
    if not people:
        await _stop(target, state, texts.REQUEST_NO_ASSIGNEES if actor else texts.TASK_NOT_ALLOWED)
        return
    data = await state.update_data(
        department_id=department_id, department_name=department_name, people=people
    )
    await state.set_state(TaskWizard.assignee)
    await target.answer(
        texts.TASK_CHOOSE_ASSIGNEE,
        reply_markup=_choices(data["nonce"], "a", [name for _, name in people], prefix=PREFIX),
    )


async def _ask_due(target: Message, state: FSMContext, nonce: str) -> None:
    await state.set_state(TaskWizard.due)
    await target.answer(
        texts.TASK_DUE, reply_markup=_buttons(nonce, [[(texts.BUTTON_NO_DUE, "nodue")]])
    )


async def _ask_priority(target: Message, state: FSMContext, nonce: str) -> None:
    await state.set_state(TaskWizard.priority)
    names = list(texts.PRIORITIES.items())
    await target.answer(
        texts.TASK_PRIORITY,
        reply_markup=_buttons(
            nonce,
            [
                [(label, f"p:{code}") for code, label in names[:2]],
                [(label, f"p:{code}") for code, label in names[2:]],
            ],
        ),
    )


async def _ask_confirmation(target: Message, state: FSMContext, data: dict[str, Any]) -> None:
    await state.set_state(TaskWizard.confirm)
    await target.answer(
        texts.task_summary(
            title=data["title"],
            description=data["description"],
            department=data["department_name"],
            assignee=str(dict(data["people"])[data["assignee_id"]]),
            due=_shown_due(data),
            priority=data["priority"],
        ),
        reply_markup=_buttons(
            data["nonce"], [[(texts.BUTTON_CREATE_TASK, "create"), (texts.BUTTON_CANCEL, "cancel")]]
        ),
    )


# --- Buttons ----------------------------------------------------------------


async def pressed(callback: CallbackQuery, state: FSMContext) -> None:
    message = callback.message
    parts = (callback.data or "").split(":")
    data = await state.get_data()
    current = await state.get_state()
    if (
        not isinstance(message, Message)
        or message.chat.type != ChatType.PRIVATE
        or current is None
        or not current.startswith("TaskWizard:")
        or len(parts) < 3
        or parts[1] != data.get("nonce")
        or data.get("telegram_user_id") != callback.from_user.id
    ):
        await callback.answer(texts.REQUEST_STALE, show_alert=True)
        return
    action, arg = parts[2], parts[3] if len(parts) > 3 else ""
    nonce = data["nonce"]
    await callback.answer()

    async def done_with_buttons() -> None:
        with suppress(TelegramAPIError):
            await message.edit_reply_markup(reply_markup=None)

    if action == "cancel":
        await done_with_buttons()
        await _stop(message, state, texts.REQUEST_CANCELLED)
    elif current == TaskWizard.department.state and action == "d":
        if (index := _index(arg, data["departments"])) is not None:
            await done_with_buttons()
            await _set_department(message, state, data, index)
    elif current == TaskWizard.assignee.state and action == "a":
        if (index := _index(arg, data["people"])) is not None:
            await done_with_buttons()
            await state.update_data(assignee_id=data["people"][index][0])
            await state.set_state(TaskWizard.title)
            await message.answer(texts.TASK_TITLE)
    elif current == TaskWizard.description.state and action == "skip":
        await done_with_buttons()
        await _ask_due(message, state, nonce)
    elif current == TaskWizard.due.state and action == "nodue":
        await done_with_buttons()
        await _ask_priority(message, state, nonce)
    elif current == TaskWizard.priority.state and action == "p" and arg in texts.PRIORITIES:
        await done_with_buttons()
        data = await state.update_data(priority=arg)
        await _ask_confirmation(message, state, data)
    elif current == TaskWizard.confirm.state and action == "create":
        await done_with_buttons()
        await _create(message, state, data)


# --- Typed answers ----------------------------------------------------------


def _typed(message: Message) -> str | None:
    text = message.text
    return None if text is None or text.startswith("/") else text


async def typed_title(message: Message, state: FSMContext) -> None:
    title = " ".join((_typed(message) or "").split())
    if not title or len(title) > 200:
        await message.answer(texts.TASK_TITLE)
        return
    data = await state.update_data(title=title)
    await state.set_state(TaskWizard.description)
    await message.answer(
        texts.TASK_DESCRIPTION,
        reply_markup=_buttons(data["nonce"], [[(texts.BUTTON_SKIP, "skip")]]),
    )


async def typed_description(message: Message, state: FSMContext) -> None:
    description = (_typed(message) or "").strip()
    if not description or len(description) > MAX_DESCRIPTION:
        await message.answer(texts.REQUEST_TYPE_TEXT)
        return
    data = await state.update_data(description=description)
    await _ask_due(message, state, data["nonce"])


async def typed_due(message: Message, state: FSMContext) -> None:
    due = parse_due(_typed(message) or "", ZoneInfo(settings.NOTIFICATION_TIME_ZONE))
    if due is None or not 2000 <= due.year <= 2200:
        await message.answer(texts.TASK_DUE_REFUSED)
        return
    data = await state.update_data(due_at=due.isoformat())
    await _ask_priority(message, state, data["nonce"])


# --- Creating ---------------------------------------------------------------


async def _create(message: Message, state: FSMContext, data: dict[str, Any]) -> None:
    # This conversation is over whatever happens: it cannot create a second task.
    await state.clear()
    actor = await domain.call(partial(_actor, data["telegram_user_id"]))
    if actor is None:
        await message.answer(texts.TASK_NOT_ALLOWED)
        return
    try:
        task = await domain.call(
            partial(
                tasks.create_task,
                actor=actor,
                title=data["title"],
                description=data["description"],
                department_id=UUID(data["department_id"]),
                assignee_id=UUID(data["assignee_id"]),
                priority=data["priority"],
                due_at=datetime.fromisoformat(data["due_at"]) if data["due_at"] else None,
            )
        )
    except DomainError:
        await message.answer(texts.TASK_REFUSED)
        return
    url = f"{settings.WEB_PUBLIC_URL}/?view=all&task={task.pk}"
    await message.answer(
        texts.task_created(
            title=task.title, assignee=str(dict(data["people"]).get(data["assignee_id"], ""))
        ),
        reply_markup=(
            gateway.link_keyboard(text=texts.BUTTON_OPEN_TASK, url=url)
            if gateway.is_linkable(url)
            else None
        ),
    )


async def other_message(message: Message) -> None:
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(texts.REQUEST_USE_BUTTONS)


def build_router() -> Router:
    router = Router(name="task-wizard")
    router.message.register(begin, Command("task"))
    router.callback_query.register(pressed, F.data.startswith(f"{PREFIX}:"))
    router.message.register(typed_title, StateFilter(TaskWizard.title))
    router.message.register(typed_description, StateFilter(TaskWizard.description))
    router.message.register(typed_due, StateFilter(TaskWizard.due))
    router.message.register(
        other_message,
        StateFilter(
            TaskWizard.department, TaskWizard.assignee, TaskWizard.priority, TaskWizard.confirm
        ),
    )
    return router
