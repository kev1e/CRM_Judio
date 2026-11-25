"""The two cookies of the sign-in flow. Both are HttpOnly: page scripts never see them.

* the attempt cookie lives for the 3 minutes of a login attempt and lets only the
  browser that sent the password collect the approved session;
* the session cookie lives until the session's absolute expiry.
"""

from datetime import datetime
from uuid import UUID

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from rest_framework.response import Response

_AUTH_PATH = "/api/v1/auth/"


def _name(base: str, *, host_prefix: bool) -> str:
    # `__Host-` makes the browser refuse the cookie unless it is Secure, has
    # Path=/ and no Domain, so a sibling subdomain cannot plant it.
    return f"__Host-{base}" if host_prefix and settings.SESSION_COOKIE_SECURE else base


def session_cookie_name() -> str:
    return _name("crm_session", host_prefix=True)


def attempt_cookie_name() -> str:
    return _name("crm_login_attempt", host_prefix=False)


def _max_age(expires_at: datetime) -> int:
    return max(int((expires_at - timezone.now()).total_seconds()), 0)


def set_session(response: Response, *, session_key: str, expires_at: datetime) -> None:
    response.set_cookie(
        session_cookie_name(),
        session_key,
        max_age=_max_age(expires_at),
        path="/",
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Lax",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(session_cookie_name(), path="/", samesite="Lax")


def set_attempt(
    response: Response, *, challenge_id: UUID, attempt_key: str, expires_at: datetime
) -> None:
    response.set_cookie(
        attempt_cookie_name(),
        f"{challenge_id}.{attempt_key}",
        max_age=_max_age(expires_at),
        path=_AUTH_PATH,
        secure=settings.SESSION_COOKIE_SECURE,
        httponly=True,
        samesite="Strict",
    )


def clear_attempt(response: Response) -> None:
    response.delete_cookie(attempt_cookie_name(), path=_AUTH_PATH, samesite="Strict")


def read_attempt(request: HttpRequest) -> tuple[UUID, str] | None:
    raw = request.COOKIES.get(attempt_cookie_name(), "")
    challenge_part, separator, attempt_key = raw.partition(".")
    if not separator or not attempt_key or len(raw) > 200:
        return None
    try:
        return UUID(challenge_part), attempt_key
    except ValueError:
        return None
