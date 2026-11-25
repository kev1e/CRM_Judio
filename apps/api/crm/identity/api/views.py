from typing import cast

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.access import services as access
from crm.common.actors import Actor
from crm.common.http import client_ip, user_agent
from crm.identity import auth, password_setup, sessions
from crm.identity.api import cookies
from crm.identity.api.serializers import (
    ErrorSerializer,
    LoginProgressSerializer,
    LoginRequestSerializer,
    LoginStartedSerializer,
    MeSerializer,
    PasswordSetupRequestSerializer,
)
from crm.identity.models import Session, User


class InvalidCredentials(APIException):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "invalid_credentials"
    default_detail = "The login or password is not correct."


class TelegramNotBound(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "telegram_not_bound"
    default_detail = "The account is not bound to Telegram yet."


class Throttled(APIException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "throttled"
    default_detail = "Too many attempts. Try again later."

    def __init__(self, retry_after: int) -> None:
        super().__init__()
        self.retry_after = retry_after


def _never_cache(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    return response


class LoginView(APIView):
    """Step 1: check the login and password, ask for approval in Telegram."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="auth_login",
        request=LoginRequestSerializer,
        responses={
            200: LoginStartedSerializer,
            401: ErrorSerializer,
            409: ErrorSerializer,
            429: ErrorSerializer,
        },
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            started = auth.start_login(
                crm_login=serializer.validated_data["login"],
                password=serializer.validated_data["password"],
                ip_address=client_ip(request),
                user_agent=user_agent(request),
            )
        except auth.ThrottledError as exc:
            raise Throttled(exc.retry_after) from None
        except auth.InvalidCredentialsError:
            raise InvalidCredentials from None
        except auth.TelegramNotBoundError:
            raise TelegramNotBound from None

        remaining = max(int((started.expires_at - timezone.now()).total_seconds()), 0)
        response = Response({"expires_at": started.expires_at, "expires_in": remaining})
        cookies.set_attempt(
            response,
            challenge_id=started.challenge_id,
            attempt_key=started.attempt_key,
            expires_at=started.expires_at,
        )
        return _never_cache(response)


class LoginCompleteView(APIView):
    """Step 2, polled by the browser that started the attempt: where the approval
    stands; once approved, opens the session."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="auth_login_complete",
        request=None,
        responses={200: LoginProgressSerializer},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        attempt = cookies.read_attempt(request)
        if attempt is None:
            return _never_cache(Response({"state": auth.LoginState.INVALID, "delivery": None}))

        challenge_id, attempt_key = attempt
        progress = auth.complete_login(
            challenge_id=challenge_id,
            attempt_key=attempt_key,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
        )
        response = Response({"state": progress.state, "delivery": progress.delivery})
        if progress.session is not None and progress.session_key is not None:
            cookies.set_session(
                response,
                session_key=progress.session_key,
                expires_at=progress.session.expires_at,
            )
        if progress.state is not auth.LoginState.PENDING:
            cookies.clear_attempt(response)
        return _never_cache(response)


class MeView(APIView):
    """Who is signed in and what they may do right now."""

    @extend_schema(
        operation_id="auth_me", responses={200: MeSerializer, 401: ErrorSerializer}, tags=["auth"]
    )
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        session = cast(Session, request.auth)
        grants = access.effective_grants(user)
        return _never_cache(
            Response(
                {
                    "user": {
                        "id": user.pk,
                        "crm_login": user.crm_login,
                        "display_name": user.display_name,
                    },
                    "session": {"expires_at": session.expires_at},
                    "permissions": {code: scope.value for code, scope in sorted(grants.items())},
                }
            )
        )


class LogoutView(APIView):
    """Ends the current session and gives up a login attempt that is still
    waiting. Answers 204 even when there is neither, so that stale cookies are
    always removed."""

    permission_classes = [AllowAny]

    @extend_schema(operation_id="auth_logout", request=None, responses={204: None}, tags=["auth"])
    def post(self, request: Request) -> Response:
        if isinstance(request.auth, Session) and isinstance(request.user, User):
            sessions.revoke(
                actor=Actor.for_user(request.user), session=request.auth, reason="logout"
            )
        if (attempt := cookies.read_attempt(request)) is not None:
            auth.cancel_login(challenge_id=attempt[0], attempt_key=attempt[1])
        response = Response(status=status.HTTP_204_NO_CONTENT)
        cookies.clear_session(response)
        cookies.clear_attempt(response)
        return _never_cache(response)


class PasswordSetupView(APIView):
    """The employee sets their first password with the one-time link from the bot.

    Does not sign anybody in: the normal login with approval in Telegram follows.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="auth_password_setup",
        request=PasswordSetupRequestSerializer,
        responses={204: None, 400: ErrorSerializer},
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = PasswordSetupRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # DomainError (bad link, weak password) becomes a 400 with its code.
        password_setup.set_initial_password(
            raw_token=serializer.validated_data["token"],
            password=serializer.validated_data["password"],
            ip_address=client_ip(request),
        )
        return _never_cache(Response(status=status.HTTP_204_NO_CONTENT))
