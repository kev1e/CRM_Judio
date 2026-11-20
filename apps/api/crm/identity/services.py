"""Identity domain services.

The only code that creates users or changes their credentials. Transport layers
(REST, CLI, bot) call these functions; they never write the User model directly.
"""

import re
from collections.abc import Iterable
from uuid import UUID

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import F

from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity.models import CRM_LOGIN_REGEX, User

_LOGIN_RE = re.compile(CRM_LOGIN_REGEX)
# Longer inputs are refused before hashing: a memory-hard hash of megabytes is a DoS lever.
MAX_PASSWORD_LENGTH = 128


def normalize_login(raw: str) -> str:
    login = raw.strip().lower()
    if not _LOGIN_RE.fullmatch(login):
        raise DomainError(
            "invalid_login",
            "The login must be 3-64 characters: Latin letters, digits, '.', '_' or '-', "
            "starting with a letter or digit.",
        )
    return login


def normalize_email(raw: str | None) -> str | None:
    if raw is None or not raw.strip():
        return None
    email = raw.strip().lower()
    try:
        validate_email(email)
    except ValidationError as exc:
        raise DomainError("invalid_email", "The email address is not valid.") from exc
    return email


def check_password_policy(raw_password: str, user: User | None = None) -> None:
    """Q13: at least 12 characters, not a common/known-compromised password.

    No character-class rules and no forced rotation — those were not approved.
    """
    if len(raw_password) > MAX_PASSWORD_LENGTH:
        raise DomainError(
            "invalid_password", f"The password must be at most {MAX_PASSWORD_LENGTH} characters."
        )
    try:
        validate_password(raw_password, user)
    except ValidationError as exc:
        raise DomainError("invalid_password", " ".join(exc.messages)) from exc


def create_user(
    *,
    actor: Actor,
    crm_login: str,
    display_name: str,
    email: str | None = None,
    password: str | None = None,
) -> User:
    """Create an account. Authorization is the caller's duty: this function is used by
    flows that have already established the right to create the user.

    Without a password the account cannot sign in until one is set.
    """
    login = normalize_login(crm_login)
    name = display_name.strip()
    if not name:
        raise DomainError("invalid_display_name", "The display name must not be empty.")

    user = User(crm_login=login, display_name=name, email=normalize_email(email))
    if password is None:
        user.set_unusable_password()
    else:
        check_password_policy(password, user)
        user.set_password(password)

    try:
        with transaction.atomic():
            user.save(force_insert=True)
            audit.record(
                actor=actor,
                action="user.created",
                entity_type="user",
                entity_id=str(user.pk),
                metadata={"crm_login": login, "has_password": password is not None},
            )
    except IntegrityError as exc:
        raise DomainError("login_or_email_taken", "The login or email is already in use.") from exc
    return user


def set_password(*, actor: Actor, user: User, raw_password: str) -> None:
    """Replace the password. Authorization is the caller's duty (see `create_user`)."""
    check_password_policy(raw_password, user)
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        locked.set_password(raw_password)
        locked.save(update_fields=["password", "updated_at"])
        audit.record(
            actor=actor,
            action="user.password_changed",
            entity_type="user",
            entity_id=str(user.pk),
        )
    user.password = locked.password


def bump_permissions_version(user_ids: Iterable[UUID]) -> int:
    """Mark everything issued for the users' previous permissions as stale (D020).

    Must run inside the transaction that changes the roles or grants.
    """
    return User.objects.filter(pk__in=list(user_ids)).update(
        permissions_version=F("permissions_version") + 1
    )
