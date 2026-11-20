from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from crm.common.exceptions import DomainError
from crm.identity import enrollment
from crm.identity.management.commands._output import operator, print_binding_token


class Command(BaseCommand):
    help = (
        "Issue a new one-time Telegram binding code for an administrator, for example when "
        "the first code expired. Works only while no administrator has bound Telegram yet. "
        "The action is audited."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--login", required=True, help="CRM login of the administrator.")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            token = enrollment.issue_first_administrator_token(
                operator=operator(), crm_login=options["login"]
            )
        except DomainError as exc:
            raise CommandError(exc.message) from exc
        print_binding_token(self, token)
