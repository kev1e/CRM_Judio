"""Entry point: `python -m crm_bot`.

Long polling, which needs no public address — the mode for local development and
for a deployment without an HTTPS ingress. Webhook mode with the secret-token
check arrives together with the reverse proxy (S6/S8).
"""

import asyncio
import logging
import os
import sys

import django


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crm.settings")
    django.setup()

    from django.conf import settings

    from crm_bot.app import ALLOWED_UPDATES, build_bot, build_dispatcher

    logger = logging.getLogger("crm_bot")
    token: str = settings.TELEGRAM_BOT_TOKEN
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN is not set: the bot has nothing to run with.")

    async def run() -> None:
        bot = build_bot(token)
        dispatcher = build_dispatcher()
        # Polling and a webhook cannot coexist; updates that queued up while the
        # bot was down are stale (a login prompt lives 3 minutes) and are dropped.
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("CRM bot is polling for updates")
        await dispatcher.start_polling(bot, allowed_updates=ALLOWED_UPDATES)

    asyncio.run(run())


if __name__ == "__main__":
    main()
