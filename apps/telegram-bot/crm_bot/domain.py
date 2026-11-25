"""Calling synchronous Django code from the bot's event loop."""

from collections.abc import Callable

from asgiref.sync import sync_to_async
from django.db import close_old_connections


async def call[T](function: Callable[[], T]) -> T:
    """Run a domain service in the worker thread, never on the event loop.

    The bot is a long-lived process: stale database connections are dropped
    before and after each call, like Django does around an HTTP request.
    """

    def run() -> T:
        close_old_connections()
        try:
            return function()
        finally:
            close_old_connections()

    return await sync_to_async(run, thread_sensitive=True)()
