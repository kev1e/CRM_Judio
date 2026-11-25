"""Facts about an HTTP request that domain services need but must not parse themselves."""

from ipaddress import ip_address

from django.conf import settings
from django.http import HttpRequest


def _valid(raw: str) -> str | None:
    try:
        return str(ip_address(raw.strip()))
    except ValueError:
        return None


def client_ip(request: HttpRequest) -> str | None:
    """The address of the client as seen by the outermost trusted proxy.

    With `TRUSTED_PROXY_HOPS = n`, the n-th entry from the right of
    X-Forwarded-For is the one written by our own outermost proxy; everything to
    its left was supplied by the client and is ignored.
    """
    hops: int = settings.TRUSTED_PROXY_HOPS
    if hops > 0:
        forwarded = [
            part for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if part.strip()
        ]
        if len(forwarded) >= hops and (address := _valid(forwarded[-hops])):
            return address
    return _valid(request.META.get("REMOTE_ADDR", ""))


def user_agent(request: HttpRequest) -> str:
    return str(request.META.get("HTTP_USER_AGENT", ""))
