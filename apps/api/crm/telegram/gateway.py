"""The only place that sends messages to Telegram from synchronous code (Celery tasks).

`get_gateway()` returns the transport named by `settings.TELEGRAM_GATEWAY`; the
default talks to the Bot API through aiogram.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast
from urllib.parse import urlsplit
from uuid import UUID

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.token import TokenValidationError
from django.conf import settings
from django.utils.module_loading import import_string

from crm.telegram import callbacks, texts
from crm.telegram.client import build_bot

REQUEST_TIMEOUT_SECONDS = 10


class TelegramUnavailableError(Exception):
    """Telegram could not be reached or answered with a temporary error. Retrying may help."""


class TelegramRefusedError(Exception):
    """Telegram refused for good: the user blocked the bot, never started it, or the
    bot is misconfigured. Retrying will not help."""


@dataclass(frozen=True, slots=True)
class LoginPrompt:
    chat_id: int
    challenge_id: UUID
    crm_login: str
    ip_address: str | None
    user_agent: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class TaskMessage:
    """A notification about a task: a plain text and a link into the CRM."""

    chat_id: int
    text: str
    url: str


class TelegramGateway(Protocol):
    def send_task_message(self, message: TaskMessage) -> int:
        """Send a notification; return Telegram's message ID."""
        ...

    def send_login_prompt(self, prompt: LoginPrompt) -> int:
        """Send the approve/deny message; return Telegram's message ID."""
        ...


def login_keyboard(challenge_id: UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.BUTTON_APPROVE,
                    callback_data=callbacks.encode_login_decision(challenge_id, approve=True),
                ),
                InlineKeyboardButton(
                    text=texts.BUTTON_DENY,
                    callback_data=callbacks.encode_login_decision(challenge_id, approve=False),
                ),
            ]
        ]
    )


def is_linkable(url: str) -> bool:
    """Whether Telegram accepts the address as a link.

    Telegram refuses host names without a dot (`localhost`): such a URL is neither
    made clickable in a message nor allowed on a button. IP addresses and real
    domains are fine.
    """
    host = urlsplit(url).hostname or ""
    return "." in host or ":" in host


def link_keyboard(*, text: str, url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=url)]])


class AiogramGateway:
    def send_login_prompt(self, prompt: LoginPrompt) -> int:
        return asyncio.run(
            self._send(
                chat_id=prompt.chat_id,
                text=texts.login_prompt(
                    crm_login=prompt.crm_login,
                    ip_address=prompt.ip_address,
                    user_agent=prompt.user_agent,
                    expires_at=prompt.expires_at,
                ),
                reply_markup=login_keyboard(prompt.challenge_id),
            )
        )

    def send_task_message(self, message: TaskMessage) -> int:
        # A button when Telegram accepts the address; otherwise the address as text.
        if is_linkable(message.url):
            text, markup = (
                message.text,
                link_keyboard(text=texts.BUTTON_OPEN_TASK, url=message.url),
            )
        else:
            text, markup = f"{message.text}\n\n{message.url}", None
        return asyncio.run(self._send(chat_id=message.chat_id, text=text, reply_markup=markup))

    async def _send(
        self, *, chat_id: int, text: str, reply_markup: InlineKeyboardMarkup | None
    ) -> int:
        token: str = settings.TELEGRAM_BOT_TOKEN
        if not token:
            raise TelegramRefusedError("TELEGRAM_BOT_TOKEN is not set.")
        try:
            bot = build_bot(token)
        except TokenValidationError as exc:
            raise TelegramRefusedError("TELEGRAM_BOT_TOKEN is not a bot token.") from exc
        try:
            message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                # Login attempts and task details stay out of forwards and saves.
                protect_content=True,
                request_timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except TelegramRetryAfter as exc:
            # Flood limit: temporary by definition (Q23).
            raise TelegramUnavailableError(type(exc).__name__) from None
        except (TelegramForbiddenError, TelegramBadRequest, TelegramUnauthorizedError) as exc:
            # Never include the exception text: it may quote the request.
            raise TelegramRefusedError(type(exc).__name__) from None
        except (TelegramAPIError, TimeoutError, OSError) as exc:
            raise TelegramUnavailableError(type(exc).__name__) from None
        finally:
            await bot.session.close()
        return message.message_id


def get_gateway() -> TelegramGateway:
    factory = import_string(settings.TELEGRAM_GATEWAY)
    return cast(TelegramGateway, factory())
