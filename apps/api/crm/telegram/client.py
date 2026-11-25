"""Building the aiogram client the same way in the worker and in the bot process."""

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from django.conf import settings

DEFAULT_API_BASE_URL = "https://api.telegram.org"


def build_bot(token: str) -> Bot:
    """A Bot that talks to `settings.TELEGRAM_API_BASE_URL`.

    The default is Telegram's own server. Another address is for a self-hosted Bot
    API server or a relay, when the hosting network cannot reach Telegram directly.
    Whoever runs that address sees the bot token and every message: it must be
    under the company's control.
    """
    base_url: str = settings.TELEGRAM_API_BASE_URL
    if base_url == DEFAULT_API_BASE_URL:
        return Bot(token=token)
    return Bot(token=token, session=AiohttpSession(api=TelegramAPIServer.from_base(base_url)))
