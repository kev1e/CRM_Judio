from typing import cast
from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.common.actors import Actor
from crm.identity.api.serializers import ErrorSerializer
from crm.identity.models import User
from crm.tasks import workflow
from crm.tasks.api.serializers import (
    WorkflowOrderSerializer,
    WorkflowRetireSerializer,
    WorkflowSerializer,
    WorkflowStatusCreateSerializer,
    WorkflowStatusUpdateSerializer,
)

# The administrator's configuration of statuses. Every operation is authorized
# by `crm.tasks.workflow` (`workflow.manage`); each answers with the whole
# configuration so the screen never shows a stale mix.

_ERRORS = {400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


def _actor(request: Request) -> Actor:
    return Actor.for_user(cast(User, request.user))


def _respond(actor: Actor, code: int = status.HTTP_200_OK) -> Response:
    response = Response(
        {
            "results": [
                {
                    "id": info.status.pk,
                    "name": info.status.name,
                    "category": info.status.category,
                    "position": info.status.position,
                    "is_active": info.status.is_active,
                    "next_status_ids": info.next_status_ids,
                    "task_count": info.task_count,
                }
                for info in workflow.configuration(actor=actor)
            ]
        },
        status=code,
    )
    response["Cache-Control"] = "no-store"
    return response


class WorkflowView(APIView):
    @extend_schema(
        operation_id="workflow_read",
        responses={200: WorkflowSerializer, 403: ErrorSerializer},
        tags=["workflow"],
    )
    def get(self, request: Request) -> Response:
        return _respond(_actor(request))

    @extend_schema(
        operation_id="workflow_create_status",
        request=WorkflowStatusCreateSerializer,
        responses={201: WorkflowSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        tags=["workflow"],
    )
    def post(self, request: Request) -> Response:
        serializer = WorkflowStatusCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        workflow.create_status(actor=actor, **serializer.validated_data)
        return _respond(actor, status.HTTP_201_CREATED)


class WorkflowStatusView(APIView):
    @extend_schema(
        operation_id="workflow_update_status",
        request=WorkflowStatusUpdateSerializer,
        responses={200: WorkflowSerializer, **_ERRORS},
        tags=["workflow"],
    )
    def patch(self, request: Request, status_id: UUID) -> Response:
        serializer = WorkflowStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        data = serializer.validated_data
        if "name" in data:
            workflow.rename_status(actor=actor, status_id=status_id, name=data["name"])
        if "next_status_ids" in data:
            workflow.set_moves(
                actor=actor, status_id=status_id, next_status_ids=data["next_status_ids"]
            )
        return _respond(actor)


class WorkflowOrderView(APIView):
    @extend_schema(
        operation_id="workflow_reorder",
        request=WorkflowOrderSerializer,
        responses={200: WorkflowSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        tags=["workflow"],
    )
    def post(self, request: Request) -> Response:
        serializer = WorkflowOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        workflow.reorder(actor=actor, status_ids=serializer.validated_data["status_ids"])
        return _respond(actor)


class WorkflowRetireView(APIView):
    @extend_schema(
        operation_id="workflow_retire_status",
        request=WorkflowRetireSerializer,
        responses={200: WorkflowSerializer, **_ERRORS},
        tags=["workflow"],
    )
    def post(self, request: Request, status_id: UUID) -> Response:
        serializer = WorkflowRetireSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        workflow.retire_status(
            actor=actor,
            status_id=status_id,
            replacement_id=serializer.validated_data["replacement_id"],
        )
        return _respond(actor)


class WorkflowRestoreView(APIView):
    @extend_schema(
        operation_id="workflow_restore_status",
        request=None,
        responses={200: WorkflowSerializer, **_ERRORS},
        tags=["workflow"],
    )
    def post(self, request: Request, status_id: UUID) -> Response:
        actor = _actor(request)
        workflow.restore_status(actor=actor, status_id=status_id)
        return _respond(actor)
