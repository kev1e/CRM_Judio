import json
from dataclasses import asdict
from typing import BinaryIO, cast
from uuid import UUID

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity.api.serializers import ErrorSerializer
from crm.identity.models import User
from crm.request_templates import submissions
from crm.request_templates.api.serializers import (
    RequestFormListSerializer,
    RequestPayloadSerializer,
    RequestSubmitSerializer,
    TaskFormSerializer,
)
from crm.request_templates.api.views import _no_store
from crm.tasks import policy
from crm.tasks import services as tasks
from crm.tasks.api.attachment_views import ENVELOPE_BYTES, LimitedUploadHandler, too_large
from crm.tasks.api.serializers import TaskCreatedSerializer
from crm.tasks.api.views import _detail

# Submitting a request by a template and reading its values. Everything is
# authorized by `crm.request_templates.submissions`.

_FILE_PREFIX = "file."


def _actor(request: Request) -> Actor:
    return Actor.for_user(cast(User, request.user))


class RequestFormsView(APIView):
    @extend_schema(
        operation_id="request_forms_list",
        responses={200: RequestFormListSerializer},
        tags=["requests"],
    )
    def get(self, request: Request) -> Response:
        results = [
            {
                "id": offer.template.pk,
                "name": offer.template.name,
                "description": offer.template.description,
                "version": offer.version.number,
                "form_fields": offer.version.fields,
                "departments": [{"id": d.pk, "name": d.name} for d in offer.departments],
            }
            for offer in submissions.offers(_actor(request))
        ]
        return _no_store({"results": results})


class RequestsView(APIView):
    parser_classes = [MultiPartParser]

    @extend_schema(
        operation_id="requests_submit",
        request={"multipart/form-data": RequestSubmitSerializer},
        responses={
            201: TaskCreatedSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            413: ErrorSerializer,
            503: ErrorSerializer,
        },
        tags=["requests"],
    )
    def post(self, request: Request) -> Response:
        declared = request.META.get("CONTENT_LENGTH") or "0"
        if not declared.isdigit() or int(declared) > settings.ATTACHMENT_MAX_BYTES + ENVELOPE_BYTES:
            raise too_large()
        handler = LimitedUploadHandler(request._request)
        request._request.upload_handlers = [handler]
        try:
            raw = request.POST.get("payload")
            uploads = request.FILES
        finally:
            if handler.exceeded:
                raise too_large()
        try:
            payload = json.loads(raw) if isinstance(raw, str) else None
        except ValueError:
            payload = None
        if not isinstance(payload, dict):
            raise DomainError("invalid_form", "The request is not a filled form.")
        serializer = RequestPayloadSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        files: dict[str, tuple[BinaryIO, str]] = {}
        for name in uploads:
            parts = uploads.getlist(name)
            upload = parts[0] if len(parts) == 1 else None
            if not name.startswith(_FILE_PREFIX) or upload is None or upload.file is None:
                raise DomainError("invalid_form", "Unexpected part of the request.")
            files[name.removeprefix(_FILE_PREFIX)] = (
                cast(BinaryIO, upload.file),
                upload.name or "",
            )

        actor = _actor(request)
        task = submissions.submit(
            actor=actor,
            template_id=data["template_id"],
            version=data["version"],
            department_id=data["department_id"],
            assignee_id=data["assignee_id"],
            title=data["title"],
            form_values=data["values"],
            files=files,
            priority=data["priority"],
            due_at=data["due_at"],
        )
        # Q02: a receipt always, the task itself only for who may read it.
        visible = policy.allowed(actor, policy.READ, task)
        body = {
            "id": task.pk,
            "title": task.title,
            "task": _detail(actor, tasks.get_task(actor, task.pk)) if visible else None,
        }
        return _no_store(body, status.HTTP_201_CREATED)


class TaskFormView(APIView):
    @extend_schema(
        operation_id="tasks_form",
        responses={200: TaskFormSerializer, 404: ErrorSerializer},
        tags=["requests"],
    )
    def get(self, request: Request, task_id: UUID) -> Response:
        form = submissions.submitted_form(_actor(request), task_id)
        return _no_store({"form": asdict(form) if form else None})
