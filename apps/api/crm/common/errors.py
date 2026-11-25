"""One error envelope for every failure the API can return.

    {"error": {"code": "<stable_machine_code>", "message": "<human text>", "details": ...}}

Stack traces, SQL and internal identifiers never leave the process.
"""

from typing import Any

from django.http import HttpRequest, JsonResponse
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from crm.common.exceptions import DomainError, PermissionDeniedError


def envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF exception handler producing the common envelope.

    Unhandled exceptions return None on purpose: Django then logs them and calls
    `server_error`, which answers without any exception detail.
    """
    if isinstance(exc, PermissionDeniedError):
        return Response(envelope(exc.code, "Permission denied."), status=403)
    if isinstance(exc, DomainError):
        # A business rule refused the request; the code is stable, the text is safe to show.
        return Response(envelope(exc.code, exc.message), status=400)

    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, exceptions.ValidationError):
        response.data = envelope(
            "validation_error", "Request validation failed.", exc.get_full_details()
        )
    elif isinstance(exc, exceptions.APIException):
        detail = exc.detail
        code = detail.code if isinstance(detail, exceptions.ErrorDetail) else exc.default_code
        details = None
        retry_after = getattr(exc, "retry_after", None)
        if isinstance(retry_after, int):
            details = {"retry_after": retry_after}
            response["Retry-After"] = str(retry_after)
        response.data = envelope(str(code), str(detail), details)
    elif response.status_code == 404:
        response.data = envelope("not_found", "Not found.")
    elif response.status_code == 403:
        response.data = envelope("permission_denied", "Permission denied.")
    return response


def bad_request(request: HttpRequest, exception: Exception) -> JsonResponse:
    return JsonResponse(envelope("bad_request", "Bad request."), status=400)


def permission_denied(request: HttpRequest, exception: Exception) -> JsonResponse:
    return JsonResponse(envelope("permission_denied", "Permission denied."), status=403)


def not_found(request: HttpRequest, exception: Exception) -> JsonResponse:
    return JsonResponse(envelope("not_found", "Not found."), status=404)


def server_error(request: HttpRequest) -> JsonResponse:
    return JsonResponse(envelope("internal_error", "Internal server error."), status=500)
