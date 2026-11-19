import pytest
from django.db import OperationalError, connection
from rest_framework.test import APIClient

from crm.system import services


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def test_health_is_ok_without_touching_dependencies(
    client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail() -> bool:
        raise AssertionError("liveness must not call dependency checks")

    monkeypatch.setattr(services, "check_database", fail)
    monkeypatch.setattr(services, "check_redis", fail)

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_ready_is_ok_with_live_postgres_and_redis(client: APIClient) -> None:
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


@pytest.mark.django_db
def test_ready_returns_503_when_database_is_unavailable(
    client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_cursor() -> None:
        raise OperationalError("connection refused: secret-host:5432 password=hunter2")

    monkeypatch.setattr(connection, "cursor", broken_cursor)

    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "fail", "redis": "ok"},
    }
    assert "hunter2" not in response.content.decode()


@pytest.mark.django_db
def test_ready_returns_503_when_redis_is_unavailable(client: APIClient, settings) -> None:  # type: ignore[no-untyped-def]
    settings.REDIS_URL = "redis://127.0.0.1:1/0"  # nothing listens on port 1

    response = client.get("/api/v1/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "checks": {"database": "ok", "redis": "fail"},
    }


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_probe_endpoints_are_read_only(client: APIClient, method: str) -> None:
    response = getattr(client, method)("/api/v1/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
