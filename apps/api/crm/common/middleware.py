"""CSRF protection for a cookie-authenticated JSON API.

A browser attaches the session cookie to requests started by any site. It also
attaches an `Origin` header that the page cannot forge. So a state-changing
request is accepted only when:

* its Origin is one of `settings.WEB_ORIGINS`, or
* it has no Origin and carries no CRM cookie — then it is not a browser acting
  with somebody's session (a script, a health probe), and has nothing to abuse.

This also covers the login endpoints (login CSRF). The session cookie is
SameSite=Lax in addition to this check.
"""

from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse

from crm.common.errors import envelope

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
COOKIE_PREFIXES = ("crm_", "__Host-crm_")


class OriginCheckMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.method not in SAFE_METHODS and not self._allowed(request):
            return JsonResponse(
                envelope("csrf_failed", "The request did not come from the CRM interface."),
                status=403,
            )
        return self.get_response(request)

    @staticmethod
    def _allowed(request: HttpRequest) -> bool:
        origin = request.headers.get("Origin")
        if origin is not None:
            return origin.rstrip("/") in settings.WEB_ORIGINS
        return not any(name.startswith(COOKIE_PREFIXES) for name in request.COOKIES)
