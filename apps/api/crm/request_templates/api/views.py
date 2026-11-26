from typing import Any, cast
from uuid import UUID

from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity.api.serializers import ErrorSerializer
from crm.identity.models import User
from crm.request_templates import services
from crm.request_templates.api.serializers import (
    TemplateCreateSerializer,
    TemplateListSerializer,
    TemplateSerializer,
    TemplateUpdateSerializer,
)
from crm.request_templates.models import RequestTemplate

# The administrator's screen. Every operation is authorized by
# `crm.request_templates.services` (`template.manage`).

_ERRORS = {400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


def _actor(request: Request) -> Actor:
    return Actor.for_user(cast(User, request.user))


def _body(template: RequestTemplate) -> dict[str, Any]:
    return {
        "id": template.pk,
        "name": template.name,
        "description": template.description,
        "is_active": template.is_active,
        "departments": [
            {"id": d.pk, "name": d.name}
            for d in sorted(template.departments.all(), key=lambda d: d.name)
        ],
        "draft_fields": template.draft_fields,
        "draft_checkpoints": template.draft_checkpoints,
        "has_unpublished_changes": template.has_unpublished_changes,
        "versions": [
            {
                "number": v.number,
                "published_at": v.published_at,
                "published_by": v.published_by.display_name,
                "form_fields": v.fields,
                "checkpoints": v.checkpoints,
            }
            for v in template.versions.select_related("published_by").order_by("-number")
        ],
    }


def _no_store(body: Any, code: int = status.HTTP_200_OK) -> Response:
    response = Response(body, status=code)
    response["Cache-Control"] = "no-store"
    return response


def _respond(actor: Actor, template_id: UUID, code: int = status.HTTP_200_OK) -> Response:
    template = services.all_templates(actor=actor).filter(pk=template_id).first()
    if template is None:
        raise DomainError("template_not_found", "No such template.")
    return _no_store(_body(template), code)


class TemplateCollectionView(APIView):
    @extend_schema(
        operation_id="request_templates_list",
        responses={200: TemplateListSerializer, 403: ErrorSerializer},
        tags=["request-templates"],
    )
    def get(self, request: Request) -> Response:
        templates = services.all_templates(actor=_actor(request))
        return _no_store({"results": [_body(template) for template in templates]})

    @extend_schema(
        operation_id="request_templates_create",
        request=TemplateCreateSerializer,
        responses={201: TemplateSerializer, 400: ErrorSerializer, 403: ErrorSerializer},
        tags=["request-templates"],
    )
    def post(self, request: Request) -> Response:
        serializer = TemplateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        template = services.create_template(actor=actor, **serializer.validated_data)
        return _respond(actor, template.pk, status.HTTP_201_CREATED)


class TemplateView(APIView):
    @extend_schema(
        operation_id="request_templates_update",
        request=TemplateUpdateSerializer,
        responses={200: TemplateSerializer, **_ERRORS},
        tags=["request-templates"],
    )
    def patch(self, request: Request, template_id: UUID) -> Response:
        serializer = TemplateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = _actor(request)
        # One save of the editor: all of it or none of it.
        with transaction.atomic():
            if data.keys() & {"name", "description", "draft_fields", "draft_checkpoints"}:
                services.update_template(
                    actor=actor,
                    template_id=template_id,
                    name=data.get("name"),
                    description=data.get("description"),
                    fields=data.get("draft_fields"),
                    checkpoints=data.get("draft_checkpoints"),
                )
            if "department_ids" in data:
                services.set_departments(
                    actor=actor, template_id=template_id, department_ids=data["department_ids"]
                )
            if "is_active" in data:
                services.set_active(actor=actor, template_id=template_id, active=data["is_active"])
        return _respond(actor, template_id)


class TemplatePublishView(APIView):
    @extend_schema(
        operation_id="request_templates_publish",
        request=None,
        responses={200: TemplateSerializer, **_ERRORS},
        tags=["request-templates"],
    )
    def post(self, request: Request, template_id: UUID) -> Response:
        actor = _actor(request)
        services.publish(actor=actor, template_id=template_id)
        return _respond(actor, template_id)
