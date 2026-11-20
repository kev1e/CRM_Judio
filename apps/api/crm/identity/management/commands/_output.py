"""Shared pieces of the installation-setup commands."""

import getpass

from django.core.management.base import BaseCommand
from django.utils import timezone

from crm.identity.enrollment import IssuedToken


def operator() -> str:
    """The operating-system account running the command, for the audit log."""
    try:
        return f"os:{getpass.getuser()}"
    except OSError, KeyError:
        return "os:unknown"


def print_binding_token(command: BaseCommand, token: IssuedToken) -> None:
    expires = timezone.localtime(token.expires_at).strftime("%Y-%m-%d %H:%M %Z")
    command.stdout.write("")
    command.stdout.write("One-time Telegram binding code (shown only now, do not share it):")
    command.stdout.write(f"  {token.value}")
    command.stdout.write(f"Valid until {expires}. Send it to the CRM bot in a private chat:")
    command.stdout.write(f"  /start {token.value}")
