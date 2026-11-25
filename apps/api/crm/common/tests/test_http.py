import pytest
from django.test import RequestFactory
from pytest_django.fixtures import Settings

from crm.common.http import client_ip


def request(remote: str, forwarded: str | None = None):  # type: ignore[no-untyped-def]
    headers = {"X-Forwarded-For": forwarded} if forwarded is not None else {}
    return RequestFactory().get("/", REMOTE_ADDR=remote, headers=headers)


def test_peer_address_is_used_without_trusted_proxies(settings: Settings) -> None:
    settings.TRUSTED_PROXY_HOPS = 0

    assert client_ip(request("192.0.2.1", "198.51.100.7")) == "192.0.2.1"


@pytest.mark.parametrize(
    ("hops", "forwarded", "expected"),
    [
        (1, "198.51.100.7", "198.51.100.7"),
        (1, "10.0.0.1, 198.51.100.7", "198.51.100.7"),
        (2, "6.6.6.6, 198.51.100.7, 172.18.0.5", "198.51.100.7"),
        (1, "2001:DB8::1", "2001:db8::1"),
        # Fewer entries than proxies, or garbage: fall back to the peer address.
        (2, "198.51.100.7", "192.0.2.1"),
        (1, "not-an-address", "192.0.2.1"),
        (1, "", "192.0.2.1"),
    ],
)
def test_forwarded_address_is_taken_from_the_trusted_end(
    settings: Settings, hops: int, forwarded: str, expected: str
) -> None:
    settings.TRUSTED_PROXY_HOPS = hops

    assert client_ip(request("192.0.2.1", forwarded)) == expected


def test_unparseable_peer_address_is_none(settings: Settings) -> None:
    settings.TRUSTED_PROXY_HOPS = 0

    assert client_ip(request("")) is None
