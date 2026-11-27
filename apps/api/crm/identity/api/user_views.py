from typing import Any, cast
from uuid import UUID

from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.common.actors import Actor
from crm.identity import enrollment, users
from crm.identity.api.serializers import (
    BindingCodeSerializer,
    ErrorSerializer,
    UserCreatedSerializer,
    UserCreateRequestSerializer,
    UserListSerializer,
    UserSerializer,
    UserUpdateRequestSerializer,
)
from crm.identity.models import User

# Every view here needs a session (the API default); what the signed-in user may
# do is decided by the domain services, never by the view.


def _actor(request: Request) -> Actor:
    return Actor.for_user(cast(User, request.user))


def _user_body(user: User) -> dict[str, Any]:
    return {
        "id": user.pk,
        "crm_login": user.crm_login,
        "display_name": user.display_name,
        "responsibility": user.responsibility,
        "email": user.email,
        "is_active": user.is_active,
        "telegram_bound": user.telegram_user_id is not None,
        "has_password": user.has_usable_password(),
        "created_at": user.created_at,
        "departments": _departments_of(user),
    }


def _departments_of(user: User) -> list[dict[str, Any]]:
    managed = set(user.managed_departments.values_list("department_id", flat=True))
    memberships = user.department_memberships.select_related("department").order_by(
        "-is_primary", "department__name"
    )
    rows = [
        {
            "id": m.department_id,
            "name": m.department.name,
            "is_primary": m.is_primary,
            "is_manager": m.department_id in managed,
        }
        for m in memberships
    ]
    member_of = {row["id"] for row in rows}
    # Managing without belonging is possible: show those departments too.
    for link in user.managed_departments.select_related("department").order_by("department__name"):
        if link.department_id not in member_of:
            rows.append(
                {
                    "id": link.department_id,
                    "name": link.department.name,
                    "is_primary": False,
                    "is_manager": True,
                }
            )
    return rows


def _binding_body(token: enrollment.IssuedToken) -> dict[str, Any]:
    return {
        "code": token.value,
        "expires_at": token.expires_at,
        "command": f"/start {token.value}",
    }


def _no_store(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    return response


def _get_user(actor: Actor, user_id: UUID) -> User:
    # Listing rights are checked first, so the existence of an account is not
    # revealed to somebody who may not see accounts at all.
    user = users.list_users(actor=actor).filter(pk=user_id).first()
    if user is None:
        raise Http404
    return user


class UserCollectionView(APIView):
    @extend_schema(
        operation_id="users_list",
        responses={200: UserListSerializer, 403: ErrorSerializer},
        tags=["users"],
    )
    def get(self, request: Request) -> Response:
        accounts = users.list_users(actor=_actor(request))
        return _no_store(Response({"results": [_user_body(user) for user in accounts]}))

    @extend_schema(
        operation_id="users_create",
        request=UserCreateRequestSerializer,
        responses={201: UserCreatedSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        tags=["users"],
    )
    def post(self, request: Request) -> Response:
        serializer = UserCreateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provisioned = users.provision_user(
            actor=_actor(request),
            crm_login=serializer.validated_data["crm_login"],
            display_name=serializer.validated_data["display_name"],
            email=serializer.validated_data.get("email") or None,
            department_id=serializer.validated_data.get("department_id"),
        )
        body = {
            "user": _user_body(provisioned.user),
            "binding": _binding_body(provisioned.binding_token),
        }
        return _no_store(Response(body, status=status.HTTP_201_CREATED))


class UserView(APIView):
    @extend_schema(
        operation_id="users_update",
        request=UserUpdateRequestSerializer,
        responses={
            200: UserSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["users"],
    )
    def patch(self, request: Request, user_id: UUID) -> Response:
        serializer = UserUpdateRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        user = _get_user(actor, user_id)
        if "responsibility" in serializer.validated_data:
            users.set_responsibility(
                actor=actor, user=user, text=serializer.validated_data["responsibility"]
            )
        return _no_store(Response(_user_body(user)))


class UserBindingCodeView(APIView):
    """Issues a fresh Telegram binding code; the previous one stops working."""

    @extend_schema(
        operation_id="users_binding_code",
        request=None,
        responses={
            200: BindingCodeSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["users"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        actor = _actor(request)
        token = users.reissue_binding_token(actor=actor, user=_get_user(actor, user_id))
        return _no_store(Response(_binding_body(token)))


def _set_active(request: Request, user_id: UUID, *, active: bool) -> Response:
    actor = _actor(request)
    user = _get_user(actor, user_id)
    if active:
        users.reactivate_user(actor=actor, user=user)
    else:
        users.deactivate_user(actor=actor, user=user)
    user.refresh_from_db()
    return _no_store(Response(_user_body(user)))


_ACTIVATION_RESPONSES = {
    200: UserSerializer,
    400: ErrorSerializer,
    403: ErrorSerializer,
    404: ErrorSerializer,
}


class UserDeactivateView(APIView):
    """Closes the account at once: sessions, pending codes and links end."""

    @extend_schema(
        operation_id="users_deactivate",
        request=None,
        responses=_ACTIVATION_RESPONSES,
        tags=["users"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        return _set_active(request, user_id, active=False)


class UserReactivateView(APIView):
    @extend_schema(
        operation_id="users_reactivate",
        request=None,
        responses=_ACTIVATION_RESPONSES,
        tags=["users"],
    )
    def post(self, request: Request, user_id: UUID) -> Response:
        return _set_active(request, user_id, active=True)
