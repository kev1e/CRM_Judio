"""Setting up a fresh installation: the first administrator.

These flows run from the command line, before anybody can sign in. Each of them
stops working once its precondition is gone, and each is audited with the
operating-system account as the actor. They are not the emergency (break-glass)
procedure of REC-02, whose details are still open.
"""

from django.db import transaction

from crm.access import services as access
from crm.common.actors import Actor
from crm.identity import enrollment, services
from crm.identity.models import User


def create_first_administrator(
    *, operator: str, crm_login: str, display_name: str, password: str
) -> tuple[User, enrollment.IssuedToken]:
    """Create the very first administrator and a one-time Telegram binding token for them.

    Refuses to run as soon as any active administrator exists.
    """
    actor = Actor.cli(operator)
    with transaction.atomic():
        # Checked first, so a second run reports the real reason instead of a taken login.
        access.claim_first_administrator_slot()
        user = services.create_user(
            actor=actor, crm_login=crm_login, display_name=display_name, password=password
        )
        access.grant_first_administrator(actor=actor, user=user)
        token = enrollment.issue_first_administrator_token(
            operator=operator, crm_login=user.crm_login
        )
    user.refresh_from_db()
    return user, token
