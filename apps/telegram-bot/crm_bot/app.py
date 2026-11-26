import logging

from aiogram import Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage, SimpleEventIsolation
from aiogram.types import ErrorEvent

from crm.telegram import texts
from crm_bot import request_wizard, task_wizard
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


def build_dispatcher(storage: BaseStorage | None = None) -> Dispatcher:
    """`storage` keeps the state of the request dialogue. The process passes a
    Redis storage with a time limit; without one the state lives in memory."""
    # One update of a chat at a time: two taps on the same button are handled
    # one after the other, and the second finds the dialogue already finished.
    dispatcher = Dispatcher(
        storage=storage or MemoryStorage(), events_isolation=SimpleEventIsolation()
    )
    dispatcher.include_router(build_router())
    dispatcher.include_router(request_wizard.build_router())
    dispatcher.include_router(task_wizard.build_router())
    dispatcher.errors.register(on_error)
    return dispatcher
