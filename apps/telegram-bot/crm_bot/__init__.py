"""The CRM Telegram bot: a thin aiogram adapter.

It holds no business rules. Handlers take facts from the Telegram update (who
sent it, in which kind of chat, which button), call the same domain services as
the HTTP API, and answer with a fixed text.
"""
