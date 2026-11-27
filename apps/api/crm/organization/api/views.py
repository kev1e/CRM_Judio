from typing import Any, cast
from uuid import UUID

from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.common.actors import Actor
from crm.identity.api.serializers import ErrorSerializer
from crm.identity.models import User
from crm.organization import services
from crm.organization.api.serializers import (
    DepartmentCreateSerializer,
    DepartmentListSerializer,
    DepartmentSerializer,
    DepartmentUpdateSerializer,
    ManagerAddSerializer,
    MemberAddSerializer,
)
from crm.organization.models import Department

# Every view needs a session (the API default). What the signed-in user may see
# or change is decided by the domain services.

_ERRORS = {400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


def _actor(request: Request) -> Actor:
    return Actor.for_user(cast(User, request.user))


def _person(user: User) -> dict[str, Any]:
    return {
        "id": user.pk,
        "crm_login": user.crm_login,
        "display_name": user.display_name,
        "responsibility": user.responsibility,
        "is_active": user.is_active,
    }


def _body(department: Department) -> dict[str, Any]:
    members = department.memberships.select_related("user").order_by("user__display_name")
    managers = department.managers.select_related("user").order_by("user__display_name")
    return {
        "id": department.pk,
        "name": department.name,
        "is_active": department.is_active,
        "members": [{**_person(m.user), "is_primary": m.is_primary} for m in members],
        "managers": [{**_person(m.user), "is_designated": m.is_designated} for m in managers],
    }


def _visible(actor: Actor, department_id: UUID) -> Department:
    # Reading rights first: an ID outside the actor's reach does not exist for them.
    department = services.visible_departments(actor=actor).filter(pk=department_id).first()
    if department is None:
        raise Http404
    return department


def _respond(actor: Actor, department_id: UUID, code: int = status.HTTP_200_OK) -> Response:
    response = Response(_body(_visible(actor, department_id)), status=code)
    response["Cache-Control"] = "no-store"
    return response


class DepartmentCollectionView(APIView):
    @extend_schema(
        operation_id="departments_list",
        responses={200: DepartmentListSerializer, 403: ErrorSerializer},
        tags=["departments"],
    )
    def get(self, request: Request) -> Response:
        departments = services.visible_departments(actor=_actor(request))
        response = Response({"results": [_body(department) for department in departments]})
        response["Cache-Control"] = "no-store"
        return response

    @extend_schema(
        operation_id="departments_create",
        request=DepartmentCreateSerializer,
        responses={201: DepartmentSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        tags=["departments"],
    )
    def post(self, request: Request) -> Response:
        serializer = DepartmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        department = services.create_department(actor=actor, name=serializer.validated_data["name"])
        return _respond(actor, department.pk, status.HTTP_201_CREATED)


class DepartmentView(APIView):
    @extend_schema(
        operation_id="departments_update",
        request=DepartmentUpdateSerializer,
        responses={200: DepartmentSerializer, **_ERRORS},
        tags=["departments"],
    )
    def patch(self, request: Request, department_id: UUID) -> Response:
        serializer = DepartmentUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        _visible(actor, department_id)
        data = serializer.validated_data
        if "name" in data:
            services.rename_department(actor=actor, department_id=department_id, name=data["name"])
        if "is_active" in data:
            services.set_department_active(
                actor=actor, department_id=department_id, active=data["is_active"]
            )
        return _respond(actor, department_id)


class DepartmentMembersView(APIView):
    @extend_schema(
        operation_id="departments_add_member",
        request=MemberAddSerializer,
        responses={200: DepartmentSerializer, **_ERRORS},
        tags=["departments"],
    )
    def post(self, request: Request, department_id: UUID) -> Response:
        serializer = MemberAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        _visible(actor, department_id)
        user_id = serializer.validated_data["user_id"]
        services.add_member(actor=actor, department_id=department_id, user_id=user_id)
        if serializer.validated_data["is_primary"]:
            services.set_primary_department(
                actor=actor, user_id=user_id, department_id=department_id
            )
        return _respond(actor, department_id)


class DepartmentMemberView(APIView):
    @extend_schema(
        operation_id="departments_remove_member",
        responses={200: DepartmentSerializer, **_ERRORS},
        tags=["departments"],
    )
    def delete(self, request: Request, department_id: UUID, user_id: UUID) -> Response:
        actor = _actor(request)
        _visible(actor, department_id)
        services.remove_member(actor=actor, department_id=department_id, user_id=user_id)
        return _respond(actor, department_id)


class DepartmentManagersView(APIView):
    @extend_schema(
        operation_id="departments_add_manager",
        request=ManagerAddSerializer,
        responses={200: DepartmentSerializer, **_ERRORS},
        tags=["departments"],
    )
    def post(self, request: Request, department_id: UUID) -> Response:
        serializer = ManagerAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        _visible(actor, department_id)
        services.add_manager(
            actor=actor,
            department_id=department_id,
            user_id=serializer.validated_data["user_id"],
            designated=serializer.validated_data["is_designated"],
        )
        return _respond(actor, department_id)


class DepartmentManagerView(APIView):
    @extend_schema(
        operation_id="departments_remove_manager",
        responses={200: DepartmentSerializer, **_ERRORS},
        tags=["departments"],
    )
    def delete(self, request: Request, department_id: UUID, user_id: UUID) -> Response:
        actor = _actor(request)
        _visible(actor, department_id)
        services.remove_manager(actor=actor, department_id=department_id, user_id=user_id)
        return _respond(actor, department_id)
