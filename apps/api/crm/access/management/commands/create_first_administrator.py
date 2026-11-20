import getpass
import sys
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from crm.access import services
from crm.common.exceptions import DomainError


def _operator() -> str:
    try:
        return f"os:{getpass.getuser()}"
    except OSError, KeyError:
        return "os:unknown"


class Command(BaseCommand):
    help = (
        "Create the first administrator account. Works only while no active administrator "
        "exists. The password is read from a prompt or from standard input, never from "
        "the command line. The action is written to the audit log."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--login", required=True, help="CRM login of the administrator.")
        parser.add_argument("--display-name", required=True, help="Name shown in the interface.")
        parser.add_argument(
            "--password-stdin",
            action="store_true",
            help="Read the password from standard input (one line) instead of prompting.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        if options["password_stdin"]:
            password = sys.stdin.readline().rstrip("\r\n")
        else:
            password = getpass.getpass("Password: ")
            if password != getpass.getpass("Password (again): "):
                raise CommandError("The passwords do not match.")
        if not password:
            raise CommandError("The password must not be empty.")

        try:
            user = services.create_first_administrator(
                operator=_operator(),
                crm_login=options["login"],
                display_name=options["display_name"],
                password=password,
            )
        except DomainError as exc:
            raise CommandError(exc.message) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Administrator '{user.crm_login}' created (id {user.pk}).")
        )
