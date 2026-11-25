from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request

from crm.identity import sessions
from crm.identity.api import cookies
from crm.identity.models import Session, User


class SessionAuthentication(BaseAuthentication):
    """Authenticates by the HttpOnly session cookie.

    The session is looked up in PostgreSQL on every request (expiry, revocation,
    active account). CSRF is handled by `OriginCheckMiddleware`.
    """

    def authenticate(self, request: Request) -> tuple[User, Session] | None:
        raw_token = request.COOKIES.get(cookies.session_cookie_name())
        if not raw_token:
            return None
        session = sessions.authenticate(raw_token)
        if session is None:
            return None
        return session.user, session

    def authenticate_header(self, request: Request) -> str:
        # Makes DRF answer 401 (not 403) when there is no valid session.
        return "Session"


class SessionAuthenticationScheme(OpenApiAuthenticationExtension):  # type: ignore[no-untyped-call]
    target_class = "crm.identity.api.authentication.SessionAuthentication"
    name = "sessionCookie"

    def get_security_definition(self, auto_schema: object) -> dict[str, str]:
        return {"type": "apiKey", "in": "cookie", "name": "crm_session"}
