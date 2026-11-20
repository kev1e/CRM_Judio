import getpass
import sys
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from crm.common.exceptions import DomainError
from crm.identity import setup
from crm.identity.management.commands._output import operator, print_binding_token


class Command(BaseCommand):
    help = (
        "Create the first administrator account. Works only while no active administrator "
        "exists. The password is read from a prompt or from standard input, never from "
        "the command line. Prints a one-time Telegram binding code. The action is audited."
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
            user, token = setup.create_first_administrator(
                operator=operator(),
                crm_login=options["login"],
                display_name=options["display_name"],
                password=password,
            )
        except DomainError as exc:
            raise CommandError(exc.message) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Administrator '{user.crm_login}' created (id {user.pk}).")
        )
        print_binding_token(self, token)
