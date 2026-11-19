import pytest
from django.test import Client

from crm.system import services


def test_unknown_route_returns_error_envelope() -> None:
    response = Client().get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.headers["Content-Type"] == "application/json"
    assert response.json() == {
        "error": {"code": "not_found", "message": "Not found.", "details": None}
    }


def test_schema_endpoint_is_not_served_by_default() -> None:
    assert Client().get("/api/schema").status_code == 404


def test_unhandled_exception_returns_envelope_without_internals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode() -> services.Readiness:
        raise RuntimeError("boom: internal detail that must not leak")

    monkeypatch.setattr(services, "get_readiness", explode)
    client = Client(raise_request_exception=False)

    response = client.get("/api/v1/ready")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error.", "details": None}
    }
    body = response.content.decode()
    assert "boom" not in body
    assert "Traceback" not in body
