"""Feeding updates to the bot without Telegram.

`RecordingSession` replaces aiogram's HTTP session: every Bot API call the
handlers make is recorded and answered locally, so a test sees exactly what the
bot would have sent.
"""

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageText,
    SendMessage,
    TelegramMethod,
)
from aiogram.methods.base import TelegramType
from aiogram.types import CallbackQuery, Chat, Message, Update, User
from asgiref.sync import sync_to_async
from django.db import connections

from crm_bot.app import build_dispatcher

BOT_TOKEN = "42:TEST-TOKEN-NOT-REAL"
BOT_ID = 42
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        return None

    async def make_request(
        self, bot: Bot, method: TelegramMethod[TelegramType], timeout: int | None = None
    ) -> TelegramType:
        self.calls.append(method)
        result: Any = True
        if isinstance(method, SendMessage | EditMessageText):
            result = Message(
                message_id=900 + len(self.calls),
                date=NOW,
                chat=Chat(id=int(getattr(method, "chat_id", 0) or 0), type="private"),
                text=method.text,
            )
        return result  # type: ignore[no-any-return]

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes]:
        if url:
            raise NotImplementedError
        yield b""

    def texts(self, kind: type[TelegramMethod[Any]]) -> list[str]:
        return [str(getattr(call, "text", "")) for call in self.calls if isinstance(call, kind)]

    def of(self, kind: type[TelegramMethod[Any]]) -> list[Any]:
        return [call for call in self.calls if isinstance(call, kind)]


def telegram_user(user_id: int, username: str | None = None) -> User:
    return User(id=user_id, is_bot=False, first_name="Тест", username=username)


def message_update(
    text: str, *, user_id: int, chat_type: str = "private", username: str | None = None
) -> Update:
    chat_id = user_id if chat_type == "private" else -100500
    return Update(
        update_id=1,
        message=Message(
            message_id=10,
            date=NOW,
            chat=Chat(id=chat_id, type=chat_type),
            from_user=telegram_user(user_id, username),
            text=text,
        ),
    )


def callback_update(data: str, *, user_id: int) -> Update:
    return Update(
        update_id=2,
        callback_query=CallbackQuery(
            id="cb-1",
            from_user=telegram_user(user_id),
            chat_instance="ci",
            data=data,
            message=Message(
                message_id=77,
                date=NOW,
                chat=Chat(id=user_id, type="private"),
                from_user=User(id=BOT_ID, is_bot=True, first_name="CRM"),
                text="Вход в CRM",
            ),
        ),
    )


def feed(update: Update) -> RecordingSession:
    """Run one update through the real dispatcher and return what the bot sent."""
    session = RecordingSession()

    async def run() -> None:
        bot = Bot(token=BOT_TOKEN, session=session)
        try:
            await build_dispatcher().feed_update(bot, update)
        finally:
            # The handlers' worker thread keeps its database connection between
            # calls; close it so the test database can be dropped at the end.
            await sync_to_async(connections.close_all, thread_sensitive=True)()

    asyncio.run(run())
    return session


__all__ = [
    "AnswerCallbackQuery",
    "DeleteMessage",
    "EditMessageText",
    "RecordingSession",
    "SendMessage",
    "callback_update",
    "feed",
    "message_update",
]
