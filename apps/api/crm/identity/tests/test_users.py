"""S1.4: provisioning and deactivating employee accounts."""

from collections.abc import Callable

import pytest
from rest_framework.test import APIClient

from crm.access import services as access
from crm.access.models import Role
from crm.access.permissions import ADMINISTRATOR_GRANTS, Scope
from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import STRONG_PASSWORD, Employee, EmployeeFactory, UserFactory
from crm.identity import auth, enrollment, password_setup, sessions, users
from crm.identity.models import (
    LoginChallenge,
    PasswordSetupToken,
    TelegramEnrollmentToken,
    User,
)

pytestmark = pytest.mark.django_db

ORIGIN = "http://127.0.0.1:3000"


def sign_in(client: APIClient, crm_login: str, telegram_user_id: int) -> None:
    client.post(
        "/api/v1/auth/login",
        {"login": crm_login, "password": STRONG_PASSWORD},
        format="json",
        headers={"Origin": ORIGIN},
    )
    challenge = LoginChallenge.objects.filter(user__crm_login=crm_login).latest("created_at")
    auth.decide_challenge(
        challenge_id=challenge.pk, telegram_user_id=telegram_user_id, approve=True
    )
    response = client.post("/api/v1/auth/login/complete", headers={"Origin": ORIGIN})
    assert response.json()["state"] == "authenticated"


@pytest.fixture
def admin_client(administrator: User) -> APIClient:
    User.objects.filter(pk=administrator.pk).update(
        telegram_user_id=424242, telegram_bound_at=administrator.created_at
    )
    client = APIClient()
    sign_in(client, administrator.crm_login, 424242)
    return client


@pytest.fixture
def employee_client(employee: Employee) -> APIClient:
    client = APIClient()
    sign_in(client, employee.user.crm_login, employee.telegram_user_id)
    return client


def post(client: APIClient, path: str, data: object = None):  # type: ignore[no-untyped-def]
    return client.post(path, data, format="json", headers={"Origin": ORIGIN})


# --- Domain -----------------------------------------------------------------


def test_administrator_role_grants_match_the_catalogue(administrator: User) -> None:
    assert "user.read" in ADMINISTRATOR_GRANTS
    assert access.effective_grants(administrator) == ADMINISTRATOR_GRANTS


def test_provisioning_creates_a_passwordless_account_with_a_binding_code(
    admin_actor: Actor,
) -> None:
    provisioned = users.provision_user(
        actor=admin_actor, crm_login="Ivan.Petrov", display_name=" Иван Петров ", email="I@X.RU"
    )

    user = provisioned.user
    assert (user.crm_login, user.display_name, user.email) == (
        "ivan.petrov",
        "Иван Петров",
        "i@x.ru",
    )
    assert not user.has_usable_password()
    assert user.telegram_user_id is None
    assert access.effective_grants(user) == {}  # no role is given implicitly
    bound = enrollment.redeem_token(
        raw_token=provisioned.binding_token.value,
        telegram_user_id=777001,
        telegram_username=None,
        chat_is_private=True,
    )
    assert bound == user
    actions = set(
        AuditEvent.objects.filter(entity_id=str(user.pk)).values_list("action", flat=True)
    )
    assert {"user.created", "telegram.enrollment_issued", "telegram.bound"} <= actions


def test_whole_onboarding_ends_with_a_working_login(admin_actor: Actor) -> None:
    provisioned = users.provision_user(actor=admin_actor, crm_login="ivan", display_name="Иван")
    enrollment.redeem_token(
        raw_token=provisioned.binding_token.value,
        telegram_user_id=777001,
        telegram_username="ivan_p",
        chat_is_private=True,
    )
    link = password_setup.issue_for_telegram_account(telegram_user_id=777001)
    assert link is not None
    password_setup.set_initial_password(
        raw_token=link.value, password=STRONG_PASSWORD, ip_address=None
    )

    started = auth.start_login(
        crm_login="ivan", password=STRONG_PASSWORD, ip_address=None, user_agent=None
    )
    auth.decide_challenge(challenge_id=started.challenge_id, telegram_user_id=777001, approve=True)
    progress = auth.complete_login(
        challenge_id=started.challenge_id,
        attempt_key=started.attempt_key,
        ip_address=None,
        user_agent=None,
    )

    assert progress.state is auth.LoginState.AUTHENTICATED


def test_duplicate_login_creates_nothing(admin_actor: Actor) -> None:
    users.provision_user(actor=admin_actor, crm_login="ivan", display_name="Иван")

    with pytest.raises(DomainError) as error:
        users.provision_user(actor=admin_actor, crm_login="IVAN", display_name="Другой")

    assert error.value.code == "login_or_email_taken"
    assert User.objects.filter(crm_login="ivan").count() == 1
    assert TelegramEnrollmentToken.objects.filter(user__crm_login="ivan").count() == 1


@pytest.mark.parametrize(
    "call",
    [
        lambda actor, target: users.list_users(actor=actor),
        lambda actor, target: users.provision_user(actor=actor, crm_login="xx1", display_name="X"),
        lambda actor, target: users.reissue_binding_token(actor=actor, user=target),
        lambda actor, target: users.deactivate_user(actor=actor, user=target),
        lambda actor, target: users.reactivate_user(actor=actor, user=target),
    ],
)
def test_actors_without_the_right_are_refused(
    call: Callable[[Actor, User], object], employee: Employee, make_user: UserFactory
) -> None:
    target = make_user("target")
    for actor in (Actor.for_user(employee.user), Actor.system("worker"), Actor.cli("os:root")):
        with pytest.raises(PermissionDeniedError):
            call(actor, target)

    assert User.objects.filter(crm_login="xx1").count() == 0
    target.refresh_from_db()
    assert target.is_active


def test_department_scoped_grant_is_not_enough_before_departments_exist(
    employee: Employee, admin_actor: Actor
) -> None:
    role = access.create_role(actor=admin_actor, key="manager", name="Руководитель")
    access.set_role_grants(
        actor=admin_actor,
        role=role,
        grants={"user.create": Scope.MANAGED_DEPARTMENTS, "user.read": Scope.MANAGED_DEPARTMENTS},
    )
    access.assign_role(actor=admin_actor, user=employee.user, role=role)
    actor = Actor.for_user(employee.user)

    with pytest.raises(PermissionDeniedError):
        users.provision_user(actor=actor, crm_login="xx1", display_name="X")
    with pytest.raises(PermissionDeniedError):
        users.list_users(actor=actor)


def test_holder_of_user_create_cannot_give_roles(employee: Employee, admin_actor: Actor) -> None:
    # Creating accounts must not become a way to create administrators.
    role = access.create_role(actor=admin_actor, key="hr", name="Кадры")
    access.set_role_grants(actor=admin_actor, role=role, grants={"user.create": Scope.COMPANY})
    access.assign_role(actor=admin_actor, user=employee.user, role=role)
    actor = Actor.for_user(employee.user)
    created = users.provision_user(actor=actor, crm_login="xx1", display_name="X").user

    with pytest.raises(PermissionDeniedError):
        access.assign_role(actor=actor, user=created, role=Role.objects.get(key="administrator"))


def test_deactivation_ends_everything_at_once(
    employee: Employee, admin_actor: Actor, make_user: UserFactory
) -> None:
    started = auth.start_login(
        crm_login=employee.user.crm_login,
        password=employee.password,
        ip_address=None,
        user_agent=None,
    )
    auth.decide_challenge(
        challenge_id=started.challenge_id, telegram_user_id=employee.telegram_user_id, approve=True
    )
    progress = auth.complete_login(
        challenge_id=started.challenge_id,
        attempt_key=started.attempt_key,
        ip_address=None,
        user_agent=None,
    )
    assert progress.session_key is not None
    version = employee.user.permissions_version

    assert users.deactivate_user(actor=admin_actor, user=employee.user) is True
    assert users.deactivate_user(actor=admin_actor, user=employee.user) is False

    assert sessions.authenticate(progress.session_key) is None
    employee.user.refresh_from_db()
    assert employee.user.is_active is False
    assert employee.user.deactivated_at is not None
    assert employee.user.permissions_version == version + 1
    with pytest.raises(auth.InvalidCredentialsError):
        auth.start_login(
            crm_login=employee.user.crm_login,
            password=employee.password,
            ip_address=None,
            user_agent=None,
        )
    assert AuditEvent.objects.filter(action="user.deactivated").count() == 1


def test_deactivation_revokes_pending_codes_and_links(admin_actor: Actor) -> None:
    waiting = users.provision_user(actor=admin_actor, crm_login="waiting", display_name="W")
    bound = users.provision_user(actor=admin_actor, crm_login="bound", display_name="B")
    enrollment.redeem_token(
        raw_token=bound.binding_token.value,
        telegram_user_id=777002,
        telegram_username=None,
        chat_is_private=True,
    )
    link = password_setup.issue_for_telegram_account(telegram_user_id=777002)
    assert link is not None

    users.deactivate_user(actor=admin_actor, user=waiting.user)
    users.deactivate_user(actor=admin_actor, user=bound.user)

    with pytest.raises(enrollment.EnrollmentRejectedError):
        enrollment.redeem_token(
            raw_token=waiting.binding_token.value,
            telegram_user_id=777003,
            telegram_username=None,
            chat_is_private=True,
        )
    assert not PasswordSetupToken.objects.filter(revoked_at__isnull=True).exists()
    # Reactivation does not bring the old code or link back.
    users.reactivate_user(actor=admin_actor, user=bound.user)
    with pytest.raises(password_setup.SetupLinkRejectedError):
        password_setup.set_initial_password(
            raw_token=link.value, password=STRONG_PASSWORD, ip_address=None
        )


def test_administrator_cannot_deactivate_themselves_or_the_last_administrator(
    administrator: User, admin_actor: Actor, make_employee: EmployeeFactory
) -> None:
    with pytest.raises(DomainError) as error:
        users.deactivate_user(actor=admin_actor, user=administrator)
    assert error.value.code == "cannot_deactivate_self"

    # A second administrator may not remove the only other one... unless one remains.
    second = make_employee("second.admin").user
    access.assign_role(actor=admin_actor, user=second, role=Role.objects.get(key="administrator"))
    assert users.deactivate_user(actor=Actor.for_user(second), user=administrator) is True
    with pytest.raises(DomainError) as last:
        users.deactivate_user(actor=Actor.for_user(second), user=second)
    assert last.value.code == "cannot_deactivate_self"
    assert access.is_administrator(second)


def test_reactivated_account_keeps_password_binding_and_roles(
    employee: Employee, admin_actor: Actor
) -> None:
    users.deactivate_user(actor=admin_actor, user=employee.user)

    assert users.reactivate_user(actor=admin_actor, user=employee.user) is True
    assert users.reactivate_user(actor=admin_actor, user=employee.user) is False

    employee.user.refresh_from_db()
    assert employee.user.is_active
    assert employee.user.telegram_user_id == employee.telegram_user_id
    auth.start_login(
        crm_login=employee.user.crm_login,
        password=employee.password,
        ip_address=None,
        user_agent=None,
    )
    assert AuditEvent.objects.filter(action="user.reactivated").count() == 1


def test_binding_code_cannot_be_reissued_for_a_bound_account(
    employee: Employee, admin_actor: Actor
) -> None:
    # Re-binding is a recovery action (Q12), not a button on the Users screen.
    with pytest.raises(DomainError) as error:
        users.reissue_binding_token(actor=admin_actor, user=employee.user)

    assert error.value.code == "telegram_already_bound"


# --- HTTP -------------------------------------------------------------------


def test_users_api_needs_a_session() -> None:
    client = APIClient()

    assert client.get("/api/v1/users").status_code == 401
    assert (
        client.post(
            "/api/v1/users", {"crm_login": "xx1", "display_name": "X"}, format="json"
        ).status_code
        == 401
    )


def test_employee_without_rights_gets_403_everywhere(
    employee_client: APIClient, make_user: UserFactory
) -> None:
    target = make_user("target")

    assert employee_client.get("/api/v1/users").status_code == 403
    assert (
        post(
            employee_client, "/api/v1/users", {"crm_login": "xx1", "display_name": "X"}
        ).status_code
        == 403
    )
    for action in ("binding-code", "deactivate", "reactivate"):
        response = post(employee_client, f"/api/v1/users/{target.pk}/{action}")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"
    target.refresh_from_db()
    assert target.is_active
    assert not User.objects.filter(crm_login="xx1").exists()


def test_administrator_lists_accounts_without_secrets(
    admin_client: APIClient, employee: Employee
) -> None:
    response = admin_client.get("/api/v1/users")

    assert response.status_code == 200
    rows = {row["crm_login"]: row for row in response.json()["results"]}
    assert set(rows) == {"root.admin", "anna.petrova"}
    assert rows["anna.petrova"] == {
        "id": str(employee.user.pk),
        "crm_login": "anna.petrova",
        "display_name": employee.user.display_name,
        "email": None,
        "is_active": True,
        "telegram_bound": True,
        "has_password": True,
        "created_at": rows["anna.petrova"]["created_at"],
        "departments": [],
    }
    body = response.content.decode()
    assert "argon2" not in body
    assert str(employee.telegram_user_id) not in body


def test_administrator_creates_an_account_and_sees_the_code_once(
    admin_client: APIClient,
) -> None:
    response = post(
        admin_client, "/api/v1/users", {"crm_login": "ivan.petrov", "display_name": "Иван Петров"}
    )

    assert response.status_code == 201
    assert response["Cache-Control"] == "no-store"
    body = response.json()
    assert body["user"]["crm_login"] == "ivan.petrov"
    assert body["user"]["has_password"] is False
    assert body["user"]["telegram_bound"] is False
    code = body["binding"]["code"]
    assert body["binding"]["command"] == f"/start {code}"
    assert code not in admin_client.get("/api/v1/users").content.decode()
    user = enrollment.redeem_token(
        raw_token=code, telegram_user_id=777001, telegram_username=None, chat_is_private=True
    )
    assert user.crm_login == "ivan.petrov"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"crm_login": "a b", "display_name": "X"}, "invalid_login"),
        ({"crm_login": "root.admin", "display_name": "X"}, "login_or_email_taken"),
        ({"crm_login": "ok.login", "display_name": "   "}, "validation_error"),
        ({"crm_login": "ok.login", "display_name": "X", "email": "nope"}, "validation_error"),
        ({"display_name": "X"}, "validation_error"),
    ],
)
def test_invalid_account_data_is_refused(
    admin_client: APIClient, payload: dict[str, str], code: str
) -> None:
    response = post(admin_client, "/api/v1/users", payload)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == code
    assert not User.objects.filter(crm_login="ok.login").exists()


def test_client_cannot_set_fields_it_was_not_asked_for(admin_client: APIClient) -> None:
    response = post(
        admin_client,
        "/api/v1/users",
        {
            "crm_login": "sneaky",
            "display_name": "X",
            "password": STRONG_PASSWORD,
            "is_active": False,
            "telegram_user_id": 1,
            "roles": ["administrator"],
        },
    )

    assert response.status_code == 201
    user = User.objects.get(crm_login="sneaky")
    assert not user.has_usable_password()
    assert user.is_active
    assert user.telegram_user_id is None
    assert access.effective_grants(user) == {}


def test_new_binding_code_replaces_the_old_one(admin_client: APIClient) -> None:
    created = post(
        admin_client, "/api/v1/users", {"crm_login": "ivan", "display_name": "Иван"}
    ).json()

    response = post(admin_client, f"/api/v1/users/{created['user']['id']}/binding-code")

    assert response.status_code == 200
    with pytest.raises(enrollment.EnrollmentRejectedError):
        enrollment.redeem_token(
            raw_token=created["binding"]["code"],
            telegram_user_id=777001,
            telegram_username=None,
            chat_is_private=True,
        )
    enrollment.redeem_token(
        raw_token=response.json()["code"],
        telegram_user_id=777002,
        telegram_username=None,
        chat_is_private=True,
    )


def test_deactivating_over_http_cuts_the_employees_session(
    admin_client: APIClient, employee_client: APIClient, employee: Employee
) -> None:
    assert employee_client.get("/api/v1/auth/me").status_code == 200

    response = post(admin_client, f"/api/v1/users/{employee.user.pk}/deactivate")

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert employee_client.get("/api/v1/auth/me").status_code == 401

    again = post(admin_client, f"/api/v1/users/{employee.user.pk}/reactivate")
    assert again.json()["is_active"] is True
    # The old session does not come back with the account.
    assert employee_client.get("/api/v1/auth/me").status_code == 401


def test_business_refusals_and_unknown_ids(admin_client: APIClient, administrator: User) -> None:
    own = post(admin_client, f"/api/v1/users/{administrator.pk}/deactivate")
    assert own.status_code == 400
    assert own.json()["error"]["code"] == "cannot_deactivate_self"

    missing = post(admin_client, "/api/v1/users/019ab3c4-0000-7000-8000-000000000001/deactivate")
    assert missing.status_code == 404


def test_password_setup_over_http(admin_actor: Actor) -> None:
    provisioned = users.provision_user(actor=admin_actor, crm_login="ivan", display_name="Иван")
    enrollment.redeem_token(
        raw_token=provisioned.binding_token.value,
        telegram_user_id=777001,
        telegram_username=None,
        chat_is_private=True,
    )
    link = password_setup.issue_for_telegram_account(telegram_user_id=777001)
    assert link is not None
    client = APIClient()

    weak = post(client, "/api/v1/auth/password/setup", {"token": link.value, "password": "short"})
    assert weak.status_code == 400
    assert weak.json()["error"]["code"] == "invalid_password"

    done = post(
        client, "/api/v1/auth/password/setup", {"token": link.value, "password": STRONG_PASSWORD}
    )
    assert done.status_code == 204
    assert not done.cookies  # setting a password signs nobody in

    replay = post(
        client, "/api/v1/auth/password/setup", {"token": link.value, "password": STRONG_PASSWORD}
    )
    assert replay.status_code == 400
    assert replay.json()["error"]["code"] == "setup_link_rejected"
    foreign = client.post(
        "/api/v1/auth/password/setup",
        {"token": "x", "password": STRONG_PASSWORD},
        format="json",
        headers={"Origin": "https://evil.example"},
    )
    assert foreign.status_code == 403
