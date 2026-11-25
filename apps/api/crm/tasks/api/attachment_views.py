from typing import Any, BinaryIO, cast
from urllib.parse import quote
from uuid import UUID

from django.conf import settings
from django.core.files.uploadhandler import StopUpload, TemporaryFileUploadHandler
from django.http import StreamingHttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity.api.serializers import ErrorSerializer
from crm.identity.models import User
from crm.tasks import attachments
from crm.tasks.api.serializers import AttachmentUploadSerializer, TaskDetailSerializer
from crm.tasks.api.views import _task_response

_ERRORS = {
    400: ErrorSerializer,
    403: ErrorSerializer,
    404: ErrorSerializer,
    413: ErrorSerializer,
    503: ErrorSerializer,
}
# Room for the multipart envelope around a file of the maximum size.
_ENVELOPE_BYTES = 1024 * 1024


def _actor(request: Request) -> Actor:
    return Actor.for_user(cast(User, request.user))


def _too_large() -> DomainError:
    return DomainError("file_too_large", "The file is larger than 100 MB.")


class _LimitedUploadHandler(TemporaryFileUploadHandler):
    """Writes the upload to a temporary file and stops reading once it is too big,
    whatever the Content-Length header said."""

    def __init__(self, request: Any = None) -> None:
        super().__init__(request)
        self.received = 0
        self.exceeded = False

    def receive_data_chunk(self, raw_data: bytes, start: int) -> bytes | None:
        self.received += len(raw_data)
        if self.received > settings.ATTACHMENT_MAX_BYTES:
            self.exceeded = True
            raise StopUpload(connection_reset=True)
        return super().receive_data_chunk(raw_data, start)


class TaskAttachmentsView(APIView):
    parser_classes = [MultiPartParser]

    @extend_schema(
        operation_id="tasks_add_attachment",
        request={"multipart/form-data": AttachmentUploadSerializer},
        responses={200: TaskDetailSerializer, **_ERRORS},
        tags=["tasks"],
    )
    def post(self, request: Request, task_id: UUID) -> Response:
        declared = request.META.get("CONTENT_LENGTH") or "0"
        if (
            not declared.isdigit()
            or int(declared) > settings.ATTACHMENT_MAX_BYTES + _ENVELOPE_BYTES
        ):
            raise _too_large()
        handler = _LimitedUploadHandler(request._request)
        request._request.upload_handlers = [handler]
        try:
            upload = request.FILES.get("file")
        finally:
            if handler.exceeded:
                raise _too_large()
        if upload is None or upload.file is None:
            raise DomainError("file_missing", "Choose a file to attach.")
        actor = _actor(request)
        attachments.add_attachment(
            actor=actor, task_id=task_id, stream=cast(BinaryIO, upload.file), name=upload.name or ""
        )
        return _task_response(actor, task_id)


class TaskAttachmentView(APIView):
    @extend_schema(
        operation_id="tasks_download_attachment",
        responses={
            200: OpenApiResponse(OpenApiTypes.BINARY, description="The file."),
            403: ErrorSerializer,
            404: ErrorSerializer,
            503: ErrorSerializer,
        },
        tags=["tasks"],
    )
    def get(self, request: Request, task_id: UUID, attachment_id: UUID) -> StreamingHttpResponse:
        attachment, chunks = attachments.open_attachment(
            actor=_actor(request), task_id=task_id, attachment_id=attachment_id
        )
        response = StreamingHttpResponse(chunks, content_type=attachment.content_type)
        response["Content-Length"] = str(attachment.byte_size)
        # Always a download, never rendered inside the CRM's origin.
        fallback = f"file.{attachment.original_name.rsplit('.', 1)[-1].lower()}"
        response["Content-Disposition"] = (
            f'attachment; filename="{fallback}"; '
            f"filename*=UTF-8''{quote(attachment.original_name, safe='')}"
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        response["Cache-Control"] = "no-store"
        return response

    @extend_schema(
        operation_id="tasks_delete_attachment",
        responses={
            200: TaskDetailSerializer,
            400: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=["tasks"],
    )
    def delete(self, request: Request, task_id: UUID, attachment_id: UUID) -> Response:
        actor = _actor(request)
        attachments.delete_attachment(actor=actor, task_id=task_id, attachment_id=attachment_id)
        return _task_response(actor, task_id)
