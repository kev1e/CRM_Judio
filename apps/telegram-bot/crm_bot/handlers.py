"""Update handlers.

Identity always comes from the update itself (`from_user.id`, supplied by
Telegram), never from text the user typed and never from the username.
"""

import logging
from contextlib import suppress
from functools import partial

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from crm.identity import auth, enrollment
from crm.telegram import callbacks, texts
from crm_bot import domain

logger = logging.getLogger(__name__)


async def start(message: Message, command: CommandObject) -> None:
    sender = message.from_user
    if sender is None or sender.is_bot:
        return
    is_private = message.chat.type == ChatType.PRIVATE
    code = (command.args or "").strip()

    if not code:
        if is_private:
            await message.answer(texts.START_HELP)
        return

    try:
        await domain.call(
            partial(
                enrollment.redeem_token,
                raw_token=code,
                telegram_user_id=sender.id,
                telegram_username=sender.username,
                chat_is_private=is_private,
            )
        )
    except enrollment.EnrollmentRejectedError:
        # The service has audited the real reason. Outside a private chat the bot
        # stays silent: it neither confirms nor discusses a code in front of others.
        if is_private:
            await message.answer(texts.ENROLLMENT_REJECTED)
        return
    finally:
        if is_private:
            # The code is useless after one try, but there is no reason to keep it on screen.
            with suppress(TelegramAPIError):
                await message.delete()

    await message.answer(texts.ENROLLMENT_DONE)


async def login_decision(callback: CallbackQuery) -> None:
    decision = callbacks.parse_login_decision(callback.data)
    if decision is None:
        await callback.answer(texts.LOGIN_NOT_VALID, show_alert=True)
        return

    try:
        outcome = await domain.call(
            partial(
                auth.decide_challenge,
                challenge_id=decision.challenge_id,
                telegram_user_id=callback.from_user.id,
                approve=decision.approve,
            )
        )
    except auth.ChallengeRejectedError:
        text = texts.LOGIN_NOT_VALID
    else:
        text = texts.LOGIN_APPROVED if outcome is auth.Decision.APPROVED else texts.LOGIN_DENIED

    await callback.answer(text, show_alert=True)
    # Remove the buttons and leave the outcome in the chat. Failing to edit the
    # message (too old, deleted) changes nothing about the decision.
    if isinstance(callback.message, Message):
        with suppress(TelegramAPIError):
            await callback.message.edit_text(text)


def build_router() -> Router:
    router = Router(name="crm")
    router.message.register(start, CommandStart())
    router.callback_query.register(login_decision, F.data.startswith("login:"))
    return router
