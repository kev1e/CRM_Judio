"""Outbound Telegram access shared by the API, the worker and the bot process.

Not a Django app: it owns no tables. Domain services reach Telegram only through
`gateway.get_gateway()`, so tests and local runs can replace the transport.
"""
