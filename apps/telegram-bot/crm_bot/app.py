import logging

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent

from crm.telegram import texts
from crm_bot.handlers import build_router

logger = logging.getLogger(__name__)

# The bot asks Telegram only for what it handles. In particular it never receives
# ordinary group messages: nothing from a chat is read, stored or mirrored.
ALLOWED_UPDATES = ["message", "callback_query"]


async def on_error(event: ErrorEvent) -> bool:
    """An unexpected failure (for example the database is down) must not kill the
    polling loop or leak details: log the type, tell the user to retry."""
    logger.error("Update handling failed: %s", type(event.exception).__name__)
    if (callback := event.update.callback_query) is not None:
        try:
            await callback.answer(texts.TEMPORARY_FAILURE, show_alert=True)
        except Exception:
            logger.warning("Could not answer the callback after a failure")
    return True


def build_dispatcher() -> Dispatcher:
    # No FSM storage yet: the bot keeps no conversation state (wizards arrive in S6).
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router())
    dispatcher.errors.register(on_error)
    return dispatcher


def build_bot(token: str) -> Bot:
    return Bot(token=token)
