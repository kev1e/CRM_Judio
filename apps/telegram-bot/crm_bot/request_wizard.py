"""`/request`: a manager fills in a request form step by step (S6; D040, Q21).

The dialogue only collects answers. Who may submit, which forms are offered,
what a valid answer is and the creation itself are the same domain services the
website uses (`crm.request_templates`); the final `submit` checks everything
again, whatever this module let through.

* Private chat only. In a group the command is ignored (the group allowlist and
  the hand-off of Q22 are not built).
* Who is talking is decided from the sender's numeric Telegram ID on every
  step, never from a name and never from the conversation's state.
* The state lives in the FSM storage with a time limit and is dropped on
  submit, cancel or any refusal. Nothing typed is logged.
"""

import io
import secrets
from contextlib import suppress
from functools import partial
from typing import Any, BinaryIO
from uuid import UUID
from zoneinfo import ZoneInfo

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from django.conf import settings

from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity import users
from crm.request_templates import submissions, values
from crm.tasks import attachments
from crm.tasks import services as tasks
from crm.telegram import gateway, texts
from crm_bot import domain

PREFIX = "rq"
# The Bot API serves files of up to 20 MB to a bot.
MAX_FILE_BYTES = 20 * 1024 * 1024
BUTTON_TEXT_LIMIT = 60


class Wizard(StatesGroup):
    template = State()
    department = State()
    assignee = State()
    title = State()
    field = State()
    confirm = State()


# --- Small helpers ----------------------------------------------------------


def _actor(telegram_user_id: int) -> Actor | None:
    user = users.active_by_telegram_id(telegram_user_id)
    return Actor.for_user(user) if user is not None else None


def _keyboard(
    nonce: str, rows: list[list[tuple[str, str]]], *, prefix: str = PREFIX
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=text[:BUTTON_TEXT_LIMIT], callback_data=f"{prefix}:{nonce}:{action}"
                )
                for text, action in row
            ]
            for row in rows
        ]
    )


def _choices(
    nonce: str, kind: str, names: list[str], *extra: tuple[str, str], prefix: str = PREFIX
) -> InlineKeyboardMarkup:
    rows = [[(name, f"{kind}:{index}")] for index, name in enumerate(names)]
    if extra:
        rows.append(list(extra))
    return _keyboard(nonce, rows, prefix=prefix)


def _index(arg: str, items: list[Any]) -> int | None:
    return int(arg) if arg.isdigit() and int(arg) < len(items) else None


async def _stop(target: Message, state: FSMContext, text: str) -> None:
    await state.clear()
    await target.answer(text)


def _fields(data: dict[str, Any]) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = data["form"]["fields"]
    return fields


def _people_ids(data: dict[str, Any]) -> set[UUID]:
    return {UUID(person_id) for person_id, _ in data["people"]}


# --- Asking -----------------------------------------------------------------


async def _ask_department(target: Message, state: FSMContext, data: dict[str, Any]) -> None:
    departments = data["form"]["departments"]
    if len(departments) == 1:
        await _set_department(target, state, data, 0)
        return
    await state.set_state(Wizard.department)
    await target.answer(
        texts.REQUEST_CHOOSE_DEPARTMENT,
        reply_markup=_choices(data["nonce"], "d", [name for _, name in departments]),
    )


async def _set_department(
    target: Message, state: FSMContext, data: dict[str, Any], index: int
) -> None:
    department_id, department_name = data["form"]["departments"][index]
    actor = await domain.call(partial(_actor, data["telegram_user_id"]))
    if actor is None:
        await _stop(target, state, texts.REQUEST_NOT_LINKED)
        return
    try:
        people = await domain.call(
            lambda: [
                (str(person.pk), person.display_name)
                for person in tasks.eligible_assignees(actor, UUID(department_id))
            ]
        )
    except DomainError:
        await _stop(target, state, texts.REQUEST_TEMPLATE_CHANGED)
        return
    if not people:
        await _stop(target, state, texts.REQUEST_NO_ASSIGNEES)
        return
    data = await state.update_data(
        department_id=department_id, department_name=department_name, people=people
    )
    await state.set_state(Wizard.assignee)
    await target.answer(
        texts.REQUEST_CHOOSE_ASSIGNEE,
        reply_markup=_choices(data["nonce"], "a", [name for _, name in people]),
    )


async def _ask_field(target: Message, state: FSMContext, data: dict[str, Any]) -> None:
    fields, index = _fields(data), data["index"]
    if index >= len(fields):
        await _ask_confirmation(target, state, data)
        return
    field = fields[index]
    kind, nonce = field["type"], data["nonce"]
    skip = () if field["required"] else ((texts.BUTTON_SKIP, "skip"),)
    markup: InlineKeyboardMarkup | None = None
    if kind == "select" and field.get("multiple"):
        picked = set(data.get("picked", []))
        names = [("✓ " if option in picked else "") + option for option in field["options"]]
        markup = _choices(nonce, "o", names, (texts.BUTTON_DONE, "done"), *skip)
    elif kind == "select":
        markup = _choices(nonce, "o", field["options"], *skip)
    elif kind == "employee":
        markup = _choices(nonce, "o", [name for _, name in data["people"]], *skip)
    elif kind == "boolean":
        markup = _keyboard(
            nonce,
            [[(texts.BUTTON_YES, "yes"), (texts.BUTTON_NO, "no")], *([list(skip)] if skip else [])],
        )
    elif skip:
        markup = _keyboard(nonce, [list(skip)])
    await state.set_state(Wizard.field)
    await target.answer(
        texts.request_question(
            label=field["label"],
            kind=kind,
            required=field["required"],
            hint=field.get("help", ""),
            currency=field.get("currency"),
            with_time=bool(field.get("with_time")),
            multiple=bool(field.get("multiple")),
            number=index + 1,
            total=len(fields),
        ),
        reply_markup=markup,
    )


def _shown(field: dict[str, Any], data: dict[str, Any]) -> str | None:
    key = field["key"]
    if field["type"] == "file":
        return str(data["files"][key]["name"]) if key in data["files"] else None
    if key not in data["values"]:
        return None
    value = data["values"][key]
    if field["type"] == "employee":
        return str(dict(data["people"]).get(value, ""))
    if field["type"] == "boolean":
        return texts.BUTTON_YES if value else texts.BUTTON_NO
    if field["type"] == "date":
        return str(data["typed"].get(key, value))
    if isinstance(value, list):
        return ", ".join(value)
    currency = field.get("currency")
    return f"{value} {currency}" if currency else str(value)


async def _ask_confirmation(target: Message, state: FSMContext, data: dict[str, Any]) -> None:
    answers = [
        (field["label"], shown)
        for field in _fields(data)
        if (shown := _shown(field, data)) is not None
    ]
    await state.set_state(Wizard.confirm)
    await target.answer(
        texts.request_summary(
            form=data["form"]["name"],
            title=data["title"],
            department=data["department_name"],
            assignee=dict(data["people"])[data["assignee_id"]],
            answers=answers,
        ),
        reply_markup=_keyboard(
            data["nonce"], [[(texts.BUTTON_SUBMIT, "submit"), (texts.BUTTON_CANCEL, "cancel")]]
        ),
    )


async def _next_field(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    data = await state.update_data(index=data["index"] + 1, picked=[])
    await _ask_field(target, state, data)


async def _accept(
    target: Message, state: FSMContext, data: dict[str, Any], raw: Any, typed: str | None = None
) -> None:
    """Check one answer by the form's own rules and move on, or ask again."""
    field = _fields(data)[data["index"]]
    try:
        values.clean_one(field, raw, people=_people_ids(data))
    except values.FormValueError as error:
        await target.answer(texts.request_refusal((error.details or {}).get("reason", "")))
        if field["type"] in ("select", "employee", "boolean"):
            # The buttons of the refused answer are gone: show them again.
            await _ask_field(target, state, data)
        return
    answers = {**data["values"], field["key"]: raw}
    shown = {**data["typed"], **({field["key"]: typed} if typed is not None else {})}
    await state.update_data(values=answers, typed=shown)
    await _next_field(target, state)


# --- Commands ---------------------------------------------------------------


async def begin(message: Message, state: FSMContext) -> None:
    sender = message.from_user
    if sender is None or sender.is_bot or message.chat.type != ChatType.PRIVATE:
        return
    await state.clear()
    actor = await domain.call(partial(_actor, sender.id))
    if actor is None:
        await message.answer(texts.REQUEST_NOT_LINKED)
        return
    forms = await domain.call(
        lambda: [
            {
                "id": str(offer.template.pk),
                "name": offer.template.name,
                "version": offer.version.number,
                "fields": offer.version.fields,
                "departments": [(str(d.pk), d.name) for d in offer.departments],
            }
            for offer in submissions.offers(actor)
        ]
    )
    if not forms:
        await message.answer(texts.REQUEST_NO_FORMS)
        return
    nonce = secrets.token_hex(3)
    await state.set_data(
        {
            "nonce": nonce,
            "attempt": secrets.token_hex(16),
            "telegram_user_id": sender.id,
            "forms": forms,
            "values": {},
            "typed": {},
            "files": {},
            "picked": [],
            "index": 0,
        }
    )
    if len(forms) == 1:
        await _set_form(message, state, 0)
        return
    await state.set_state(Wizard.template)
    await message.answer(
        texts.REQUEST_CHOOSE_FORM,
        reply_markup=_choices(nonce, "t", [form["name"] for form in forms]),
    )


async def _set_form(target: Message, state: FSMContext, index: int) -> None:
    data = await state.get_data()
    form = data["forms"][index]
    # The other forms are not needed any more.
    data = await state.update_data(form=form, forms=[], title=form["name"])
    await _ask_department(target, state, data)


async def cancel(message: Message, state: FSMContext) -> None:
    if message.chat.type != ChatType.PRIVATE:
        return
    if await state.get_state() is None:
        await message.answer(texts.REQUEST_NOTHING_TO_CANCEL)
        return
    await _stop(message, state, texts.REQUEST_CANCELLED)


# --- Buttons ----------------------------------------------------------------


async def pressed(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    message = callback.message
    parts = (callback.data or "").split(":")
    data = await state.get_data()
    current = await state.get_state()
    if (
        not isinstance(message, Message)
        or message.chat.type != ChatType.PRIVATE
        or current is None
        or not current.startswith("Wizard:")
        or len(parts) < 3
        or parts[1] != data.get("nonce")
        or data.get("telegram_user_id") != callback.from_user.id
    ):
        await callback.answer(texts.REQUEST_STALE, show_alert=True)
        return
    action, arg = parts[2], parts[3] if len(parts) > 3 else ""
    await callback.answer()

    async def done_with_buttons() -> None:
        with suppress(TelegramAPIError):
            await message.edit_reply_markup(reply_markup=None)

    if action == "cancel":
        await done_with_buttons()
        await _stop(message, state, texts.REQUEST_CANCELLED)
    elif current == Wizard.template.state and action == "t":
        if (index := _index(arg, data["forms"])) is not None:
            await done_with_buttons()
            await _set_form(message, state, index)
    elif current == Wizard.department.state and action == "d":
        if (index := _index(arg, data["form"]["departments"])) is not None:
            await done_with_buttons()
            await _set_department(message, state, data, index)
    elif current == Wizard.assignee.state and action == "a":
        if (index := _index(arg, data["people"])) is not None:
            await done_with_buttons()
            data = await state.update_data(assignee_id=data["people"][index][0])
            await state.set_state(Wizard.title)
            await message.answer(
                texts.request_title(default=data["title"]),
                reply_markup=_keyboard(
                    data["nonce"], [[(texts.button_keep_title(data["title"]), "keep")]]
                ),
            )
    elif current == Wizard.title.state and action == "keep":
        await done_with_buttons()
        await _ask_field(message, state, data)
    elif current == Wizard.field.state:
        await _field_button(message, state, data, action, arg, done_with_buttons)
    elif current == Wizard.confirm.state and action == "submit":
        await done_with_buttons()
        await _submit(message, state, data, bot)


async def _field_button(
    message: Message,
    state: FSMContext,
    data: dict[str, Any],
    action: str,
    arg: str,
    done_with_buttons: Any,
) -> None:
    field = _fields(data)[data["index"]]
    kind = field["type"]
    if action == "skip" and not field["required"]:
        await done_with_buttons()
        await _next_field(message, state)
    elif kind == "boolean" and action in ("yes", "no"):
        await done_with_buttons()
        await _accept(message, state, data, action == "yes")
    elif kind == "employee" and action == "o":
        if (index := _index(arg, data["people"])) is not None:
            await done_with_buttons()
            await _accept(message, state, data, data["people"][index][0])
    elif kind == "select" and action == "o":
        if (index := _index(arg, field["options"])) is None:
            return
        option = field["options"][index]
        if not field.get("multiple"):
            await done_with_buttons()
            await _accept(message, state, data, option)
            return
        picked = list(data.get("picked", []))
        picked.remove(option) if option in picked else picked.append(option)
        data = await state.update_data(picked=picked)
        names = [("✓ " if item in picked else "") + item for item in field["options"]]
        skip = () if field["required"] else ((texts.BUTTON_SKIP, "skip"),)
        with suppress(TelegramAPIError):
            await message.edit_reply_markup(
                reply_markup=_choices(data["nonce"], "o", names, (texts.BUTTON_DONE, "done"), *skip)
            )
    elif kind == "select" and field.get("multiple") and action == "done":
        await done_with_buttons()
        await _accept(message, state, data, list(data.get("picked", [])))


# --- Typed answers and files ------------------------------------------------


async def typed_title(message: Message, state: FSMContext) -> None:
    title = " ".join((message.text or "").split())
    if not title or len(title) > 200 or title.startswith("/"):
        await message.answer(texts.REQUEST_TYPE_TEXT)
        return
    data = await state.update_data(title=title)
    await _ask_field(message, state, data)


async def typed_answer(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    field = _fields(data)[data["index"]]
    kind = field["type"]
    if kind == "file":
        await _file_answer(message, state, data, field, bot)
        return
    if kind in ("select", "employee", "boolean"):
        await message.answer(texts.REQUEST_USE_BUTTONS)
        return
    text = message.text
    if text is None or text.startswith("/"):
        await message.answer(texts.REQUEST_TYPE_TEXT)
        return
    if kind == "date":
        zone = ZoneInfo(settings.NOTIFICATION_TIME_ZONE)
        await _accept(
            message, state, data, values.date_from_text(field, text, zone), typed=text.strip()
        )
    else:
        await _accept(message, state, data, text)


async def _download(bot: Bot, file_id: str) -> BinaryIO | None:
    buffer = io.BytesIO()
    try:
        await bot.download(file_id, destination=buffer)
    except TelegramAPIError, OSError, TimeoutError:
        return None
    buffer.seek(0)
    return buffer


async def _file_answer(
    message: Message, state: FSMContext, data: dict[str, Any], field: dict[str, Any], bot: Bot
) -> None:
    if message.document is not None:
        file_id, size = message.document.file_id, message.document.file_size or 0
        name = message.document.file_name or "file"
    elif message.photo:
        photo = message.photo[-1]  # the largest size
        file_id, size, name = photo.file_id, photo.file_size or 0, "photo.jpg"
    else:
        await message.answer(texts.REQUEST_SEND_FILE)
        return
    if size > MAX_FILE_BYTES:
        await message.answer(texts.REQUEST_FILE_TOO_LARGE)
        return
    stream = await _download(bot, file_id)
    if stream is None:
        await message.answer(texts.REQUEST_FILE_FAILED)
        return
    try:
        # The content rules of attachments (Q16), before going any further.
        checked = attachments.check_file(stream, name)
    except DomainError:
        await message.answer(texts.REQUEST_FILE_REFUSED)
        return
    files = {**data["files"], field["key"]: {"file_id": file_id, "name": checked.name}}
    await state.update_data(files=files)
    await _next_field(message, state)


# --- Submitting -------------------------------------------------------------


async def _submit(message: Message, state: FSMContext, data: dict[str, Any], bot: Bot) -> None:
    # Whatever happens next, this conversation is over: no second submit from it.
    await state.clear()
    actor = await domain.call(partial(_actor, data["telegram_user_id"]))
    if actor is None:
        await message.answer(texts.REQUEST_NOT_LINKED)
        return
    files: dict[str, tuple[BinaryIO, str]] = {}
    for key, stored in data["files"].items():
        stream = await _download(bot, stored["file_id"])
        if stream is None:
            await message.answer(texts.REQUEST_REFUSED)
            return
        files[key] = (stream, stored["name"])
    form = data["form"]
    try:
        task = await domain.call(
            partial(
                submissions.submit,
                actor=actor,
                template_id=UUID(form["id"]),
                version=form["version"],
                department_id=UUID(data["department_id"]),
                assignee_id=UUID(data["assignee_id"]),
                title=data["title"],
                form_values=data["values"],
                files=files,
                source="telegram",
                idempotency_key=data["attempt"],
            )
        )
    except DomainError as error:
        changed = error.code in ("template_changed", "template_not_found", "permission_denied")
        await message.answer(texts.REQUEST_TEMPLATE_CHANGED if changed else texts.REQUEST_REFUSED)
        return
    url = f"{settings.WEB_PUBLIC_URL}/?view=all&task={task.pk}"
    await message.answer(
        texts.request_created(
            title=task.title, assignee=dict(data["people"]).get(data["assignee_id"], "")
        ),
        reply_markup=(
            gateway.link_keyboard(text=texts.BUTTON_OPEN_TASK, url=url)
            if gateway.is_linkable(url)
            else None
        ),
    )


async def other_message(message: Message) -> None:
    """Something that is not an answer while buttons are expected."""
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(texts.REQUEST_USE_BUTTONS)


def build_router() -> Router:
    router = Router(name="request-wizard")
    router.message.register(begin, Command("request"))
    router.message.register(cancel, Command("cancel"))
    router.callback_query.register(pressed, F.data.startswith(f"{PREFIX}:"))
    router.message.register(typed_title, StateFilter(Wizard.title), F.text)
    router.message.register(typed_answer, StateFilter(Wizard.field))
    router.message.register(
        other_message,
        StateFilter(
            Wizard.template, Wizard.department, Wizard.assignee, Wizard.title, Wizard.confirm
        ),
    )
    return router
