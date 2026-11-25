"""Sign-in over HTTP: cookies, CSRF/origin control, 401 by default, immediate revocation."""

from datetime import timedelta
from http.cookies import Morsel

import pytest
from django.utils import timezone
from pytest_django.fixtures import Settings
from rest_framework.test import APIClient

from crm.access import services as access
from crm.access.permissions import Scope
from crm.common.actors import Actor
from crm.conftest import Employee, EmployeeFactory
from crm.identity import auth
from crm.identity.models import LoginChallenge, Session, User

pytestmark = pytest.mark.django_db

ORIGIN = "http://127.0.0.1:3000"
SESSION_COOKIE = "__Host-crm_session"
ATTEMPT_COOKIE = "crm_login_attempt"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def post(client: APIClient, path: str, data: object = None, origin: str | None = ORIGIN):  # type: ignore[no-untyped-def]
    headers = {"Origin": origin} if origin else {}
    return client.post(path, data, format="json", headers=headers)


def login(client: APIClient, employee: Employee, password: str | None = None):  # type: ignore[no-untyped-def]
    return post(
        client,
        "/api/v1/auth/login",
        {"login": employee.user.crm_login, "password": password or employee.password},
    )


def approve_latest(employee: Employee) -> None:
    challenge = LoginChallenge.objects.filter(user=employee.user).latest("created_at")
    auth.decide_challenge(
        challenge_id=challenge.pk, telegram_user_id=employee.telegram_user_id, approve=True
    )


def sign_in(client: APIClient, employee: Employee) -> None:
    assert login(client, employee).status_code == 200
    approve_latest(employee)
    response = post(client, "/api/v1/auth/login/complete")
    assert response.json()["state"] == "authenticated"


def cookie(response, name: str) -> Morsel[str]:  # type: ignore[no-untyped-def]
    return response.cookies[name]  # type: ignore[no-any-return]


# --- Login ------------------------------------------------------------------


def test_login_starts_an_attempt_and_sets_only_an_httponly_attempt_cookie(
    client: APIClient, employee: Employee
) -> None:
    response = login(client, employee)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"expires_at", "expires_in"}
    assert 170 <= body["expires_in"] <= 180
    assert response["Cache-Control"] == "no-store"
    attempt = cookie(response, ATTEMPT_COOKIE)
    assert attempt["httponly"] is True
    assert attempt["secure"] is True
    assert attempt["samesite"] == "Strict"
    assert attempt["path"] == "/api/v1/auth/"
    assert 0 < int(attempt["max-age"]) <= 180
    assert SESSION_COOKIE not in response.cookies
    # The secret that collects the session never appears in a response body.
    assert attempt.value.split(".", 1)[1] not in response.content.decode()


def test_wrong_password_and_unknown_login_look_the_same(
    client: APIClient, employee: Employee
) -> None:
    wrong = login(client, employee, password="wrong-password-123")
    unknown = post(
        client, "/api/v1/auth/login", {"login": "nobody", "password": "wrong-password-123"}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert wrong.json()["error"]["code"] == "invalid_credentials"
    assert ATTEMPT_COOKIE not in wrong.cookies


def test_login_validates_the_body(client: APIClient) -> None:
    response = post(client, "/api/v1/auth/login", {"login": "anna"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_throttled_login_answers_429_with_retry_after(
    client: APIClient, employee: Employee
) -> None:
    for _ in range(4):
        login(client, employee, password="wrong-password-123")

    response = login(client, employee)

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "throttled"
    retry_after = response.json()["error"]["details"]["retry_after"]
    assert retry_after > 0
    assert response["Retry-After"] == str(retry_after)


def test_account_without_telegram_gets_409(client: APIClient, make_user) -> None:  # type: ignore[no-untyped-def]
    make_user("not.bound", password="plum-orbit-candle-73")

    response = post(
        client, "/api/v1/auth/login", {"login": "not.bound", "password": "plum-orbit-candle-73"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "telegram_not_bound"


# --- Completing -------------------------------------------------------------


def test_complete_reports_pending_then_opens_the_session(
    client: APIClient, employee: Employee
) -> None:
    login(client, employee)

    waiting = post(client, "/api/v1/auth/login/complete")
    assert waiting.json() == {"state": "pending", "delivery": "pending"}
    assert SESSION_COOKIE not in waiting.cookies

    approve_latest(employee)
    done = post(client, "/api/v1/auth/login/complete")

    assert done.json() == {"state": "authenticated", "delivery": None}
    session_cookie = cookie(done, SESSION_COOKIE)
    assert session_cookie["httponly"] is True
    assert session_cookie["secure"] is True
    assert session_cookie["samesite"] == "Lax"
    assert session_cookie["path"] == "/"
    assert 12 * 3600 - 10 <= int(session_cookie["max-age"]) <= 12 * 3600
    assert session_cookie.value not in done.content.decode()
    # The attempt cookie is removed once the attempt is over.
    assert cookie(done, ATTEMPT_COOKIE).value == ""


def test_complete_without_an_attempt_cookie_is_invalid(client: APIClient) -> None:
    response = post(client, "/api/v1/auth/login/complete")

    assert response.status_code == 200
    assert response.json() == {"state": "invalid", "delivery": None}


def test_another_browser_cannot_collect_an_approved_session(
    client: APIClient, employee: Employee
) -> None:
    login(client, employee)
    approve_latest(employee)
    challenge = LoginChallenge.objects.get()
    stranger = APIClient()
    stranger.cookies[ATTEMPT_COOKIE] = f"{challenge.pk}.guessed-key"

    response = post(stranger, "/api/v1/auth/login/complete")

    assert response.json()["state"] == "invalid"
    assert SESSION_COOKIE not in response.cookies
    assert not Session.objects.exists()


def test_denied_attempt_is_reported(client: APIClient, employee: Employee) -> None:
    login(client, employee)
    auth.decide_challenge(
        challenge_id=LoginChallenge.objects.get().pk,
        telegram_user_id=employee.telegram_user_id,
        approve=False,
    )

    response = post(client, "/api/v1/auth/login/complete")

    assert response.json() == {"state": "denied", "delivery": None}
    assert SESSION_COOKIE not in response.cookies


# --- Session ----------------------------------------------------------------


def test_everything_else_needs_a_session(client: APIClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_me_returns_the_user_and_live_permissions(client: APIClient, employee: Employee) -> None:
    sign_in(client, employee)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {
        "id": str(employee.user.pk),
        "crm_login": "anna.petrova",
        "display_name": employee.user.display_name,
    }
    assert body["permissions"] == {}
    assert body["session"]["expires_at"]
    assert "password" not in response.content.decode()


def test_granted_and_revoked_rights_show_up_without_a_new_login(
    client: APIClient, employee: Employee, admin_actor: Actor
) -> None:
    # D020: permission changes apply to an open session at once.
    sign_in(client, employee)
    role = access.create_role(actor=admin_actor, key="auditor", name="Аудитор")
    access.set_role_grants(actor=admin_actor, role=role, grants={"audit.read": Scope.COMPANY})

    access.assign_role(actor=admin_actor, user=employee.user, role=role)
    assert client.get("/api/v1/auth/me").json()["permissions"] == {"audit.read": "company"}

    access.revoke_role(actor=admin_actor, user=employee.user, role=role)
    assert client.get("/api/v1/auth/me").json()["permissions"] == {}


def test_deactivation_cuts_the_open_session(client: APIClient, employee: Employee) -> None:
    sign_in(client, employee)
    assert client.get("/api/v1/auth/me").status_code == 200

    User.objects.filter(pk=employee.user.pk).update(is_active=False, deactivated_at=timezone.now())

    assert client.get("/api/v1/auth/me").status_code == 401


def test_session_is_refused_after_twelve_hours(client: APIClient, employee: Employee) -> None:
    sign_in(client, employee)
    session = Session.objects.get()
    shift = timedelta(hours=12, seconds=1)
    Session.objects.filter(pk=session.pk).update(
        created_at=session.created_at - shift, expires_at=session.expires_at - shift
    )

    assert client.get("/api/v1/auth/me").status_code == 401


def test_forged_session_cookie_is_refused(client: APIClient, employee: Employee) -> None:
    sign_in(client, employee)
    client.cookies[SESSION_COOKIE] = "forged-value"

    assert client.get("/api/v1/auth/me").status_code == 401


def test_one_users_session_never_identifies_another(
    employee: Employee, make_employee: EmployeeFactory
) -> None:
    colleague = make_employee("boris.ivanov")
    first, second = APIClient(), APIClient()
    sign_in(first, employee)
    sign_in(second, colleague)

    assert first.get("/api/v1/auth/me").json()["user"]["crm_login"] == "anna.petrova"
    assert second.get("/api/v1/auth/me").json()["user"]["crm_login"] == "boris.ivanov"


# --- Logout -----------------------------------------------------------------


def test_logout_revokes_the_session_and_clears_the_cookie(
    client: APIClient, employee: Employee
) -> None:
    sign_in(client, employee)
    token = client.cookies[SESSION_COOKIE].value

    response = post(client, "/api/v1/auth/logout")

    assert response.status_code == 204
    assert cookie(response, SESSION_COOKIE).value == ""
    assert Session.objects.get().revoked_reason == "logout"
    # The old token is dead even if somebody kept a copy of it.
    replay = APIClient()
    replay.cookies[SESSION_COOKIE] = token
    assert replay.get("/api/v1/auth/me").status_code == 401


def test_logout_without_a_session_still_answers_204(client: APIClient) -> None:
    assert post(client, "/api/v1/auth/logout").status_code == 204


# --- CSRF / origin ----------------------------------------------------------


def test_state_changing_request_from_a_foreign_site_is_refused(
    client: APIClient, employee: Employee
) -> None:
    sign_in(client, employee)

    response = post(client, "/api/v1/auth/logout", origin="https://evil.example")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
    assert Session.objects.get().revoked_at is None


def test_cookie_request_without_an_origin_is_refused(client: APIClient, employee: Employee) -> None:
    sign_in(client, employee)

    response = post(client, "/api/v1/auth/logout", origin=None)

    assert response.status_code == 403
    assert Session.objects.get().revoked_at is None


def test_login_from_a_foreign_site_is_refused(client: APIClient, employee: Employee) -> None:
    response = post(
        client,
        "/api/v1/auth/login",
        {"login": employee.user.crm_login, "password": employee.password},
        origin="https://evil.example",
    )

    assert response.status_code == 403
    assert not LoginChallenge.objects.exists()


def test_script_without_cookies_or_origin_may_call_the_login(
    client: APIClient, employee: Employee
) -> None:
    response = post(
        client,
        "/api/v1/auth/login",
        {"login": employee.user.crm_login, "password": employee.password},
        origin=None,
    )

    assert response.status_code == 200


def test_reads_are_not_subject_to_the_origin_check(client: APIClient) -> None:
    response = client.get("/api/v1/health", headers={"Origin": "https://evil.example"})

    assert response.status_code == 200


def test_insecure_cookie_mode_drops_the_host_prefix(
    client: APIClient, employee: Employee, settings: Settings
) -> None:
    settings.SESSION_COOKIE_SECURE = False
    login(client, employee)
    approve_latest(employee)

    response = post(client, "/api/v1/auth/login/complete")

    assert cookie(response, "crm_session")["secure"] == ""
    assert client.get("/api/v1/auth/me").status_code == 200


# --- Client address ---------------------------------------------------------


def test_forwarded_address_is_ignored_unless_a_proxy_is_trusted(
    client: APIClient, employee: Employee, settings: Settings
) -> None:
    client.post(
        "/api/v1/auth/login",
        {"login": employee.user.crm_login, "password": employee.password},
        format="json",
        headers={"Origin": ORIGIN, "X-Forwarded-For": "198.51.100.7"},
    )
    assert LoginChallenge.objects.latest("created_at").ip_address == "127.0.0.1"

    settings.TRUSTED_PROXY_HOPS = 1
    client.post(
        "/api/v1/auth/login",
        {"login": employee.user.crm_login, "password": employee.password},
        format="json",
        # The client forged the first entry; our proxy appended the real one.
        headers={"Origin": ORIGIN, "X-Forwarded-For": "10.10.10.10, 198.51.100.7"},
    )
    assert LoginChallenge.objects.latest("created_at").ip_address == "198.51.100.7"
