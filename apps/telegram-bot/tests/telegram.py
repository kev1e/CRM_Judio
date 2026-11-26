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
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.storage.base import BaseStorage
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageReplyMarkup,
    EditMessageText,
    GetFile,
    SendMessage,
    TelegramMethod,
)
from aiogram.methods.base import TelegramType
from aiogram.types import CallbackQuery, Chat, Document, File, Message, Update, User
from asgiref.sync import sync_to_async
from django.db import connections

from crm_bot.app import build_dispatcher

BOT_TOKEN = "42:TEST-TOKEN-NOT-REAL"
BOT_ID = 42
NOW = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)


class RecordingSession(BaseSession):
    # Files "stored at Telegram": file_id -> content. Set by a test.
    files: dict[str, bytes] = {}

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
        if isinstance(method, GetFile):
            if method.file_id not in self.files:
                raise TelegramBadRequest(method=method, message="file is too big")
            result = File(
                file_id=method.file_id, file_unique_id=method.file_id, file_path=method.file_id
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
        yield self.files[url.rsplit("/", 1)[-1]]

    def texts(self, kind: type[TelegramMethod[Any]]) -> list[str]:
        return [str(getattr(call, "text", "")) for call in self.calls if isinstance(call, kind)]

    def of(self, kind: type[TelegramMethod[Any]]) -> list[Any]:
        return [call for call in self.calls if isinstance(call, kind)]


def telegram_user(user_id: int, username: str | None = None) -> User:
    return User(id=user_id, is_bot=False, first_name="Тест", username=username)


def message_update(
    text: str | None,
    *,
    user_id: int,
    chat_type: str = "private",
    username: str | None = None,
    document: Document | None = None,
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
            document=document,
        ),
    )


def document_update(name: str, content: bytes, *, user_id: int, size: int | None = None) -> Update:
    """A file sent to the bot; its bytes become downloadable in the recording session."""
    file_id = f"file-{len(RecordingSession.files) + 1}"
    RecordingSession.files[file_id] = content
    document = Document(
        file_id=file_id,
        file_unique_id=file_id,
        file_name=name,
        file_size=len(content) if size is None else size,
    )
    return message_update(None, user_id=user_id, document=document)


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


def feed(update: Update, storage: BaseStorage | None = None) -> RecordingSession:
    """Run one update through the real dispatcher and return what the bot sent.
    Pass the same `storage` to several calls to continue a conversation."""
    session = RecordingSession()

    async def run() -> None:
        bot = Bot(token=BOT_TOKEN, session=session)
        try:
            await build_dispatcher(storage).feed_update(bot, update)
        finally:
            # The handlers' worker thread keeps its database connection between
            # calls; close it so the test database can be dropped at the end.
            await sync_to_async(connections.close_all, thread_sensitive=True)()

    asyncio.run(run())
    return session


__all__ = [
    "AnswerCallbackQuery",
    "DeleteMessage",
    "EditMessageReplyMarkup",
    "EditMessageText",
    "RecordingSession",
    "SendMessage",
    "callback_update",
    "document_update",
    "feed",
    "message_update",
]
