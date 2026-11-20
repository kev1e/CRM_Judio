import pytest
from django.db.models import F

from crm.audit.models import AuditEvent
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.conftest import STRONG_PASSWORD, UserFactory
from crm.identity import services
from crm.identity.models import User

pytestmark = pytest.mark.django_db

SYSTEM = Actor.system("tests")


@pytest.mark.parametrize(
    ("raw", "expected"), [("  Ivan.Petrov ", "ivan.petrov"), ("QA_1", "qa_1"), ("a-b", "a-b")]
)
def test_login_is_trimmed_and_lowercased(raw: str, expected: str) -> None:
    assert services.normalize_login(raw) == expected


@pytest.mark.parametrize("raw", ["", "ab", "has space", "иван", ".dot", "a" * 65, "semi;colon"])
def test_malformed_login_is_refused(raw: str) -> None:
    with pytest.raises(DomainError) as error:
        services.normalize_login(raw)
    assert error.value.code == "invalid_login"


def test_create_user_writes_audit_without_secrets() -> None:
    user = services.create_user(
        actor=SYSTEM, crm_login="Ivan", display_name=" Иван ", password=STRONG_PASSWORD
    )

    assert user.crm_login == "ivan"
    assert user.display_name == "Иван"
    event = AuditEvent.objects.get(action="user.created")
    assert event.entity_id == str(user.pk)
    assert event.actor_type == "system"
    assert event.actor_label == "tests"
    assert event.metadata == {"crm_login": "ivan", "has_password": True}
    assert STRONG_PASSWORD not in str(event.metadata)


def test_user_without_password_cannot_authenticate_by_password() -> None:
    user = services.create_user(actor=SYSTEM, crm_login="nopass", display_name="No Pass")

    assert user.has_usable_password() is False
    assert user.check_password("") is False
    assert AuditEvent.objects.get(action="user.created").metadata["has_password"] is False


def test_password_is_stored_as_argon2id_hash() -> None:
    user = services.create_user(
        actor=SYSTEM, crm_login="hashed", display_name="H", password=STRONG_PASSWORD
    )

    assert user.password.startswith("argon2$argon2id$")
    assert STRONG_PASSWORD not in user.password
    assert user.check_password(STRONG_PASSWORD) is True
    assert user.check_password(STRONG_PASSWORD + "x") is False


@pytest.mark.parametrize(
    "password",
    [
        "short-11chr",  # 11 characters
        "password1234",  # 12 characters but in the common-password list
        "x" * 129,  # too long to hash safely
    ],
)
def test_q13_weak_passwords_are_refused_and_nothing_is_created(password: str) -> None:
    with pytest.raises(DomainError) as error:
        services.create_user(actor=SYSTEM, crm_login="weak", display_name="W", password=password)

    assert error.value.code == "invalid_password"
    assert not User.objects.filter(crm_login="weak").exists()
    assert not AuditEvent.objects.exists()


@pytest.mark.parametrize(
    "password", ["alllowercaseletters", "twelve chars", "748215963047", "ЭтоДлинныйПароль"]
)
def test_q13_no_character_class_rules(password: str) -> None:
    # Q13 asks for length and a compromised-password check only.
    services.check_password_policy(password)


def test_duplicate_login_or_email_is_a_domain_error(make_user: UserFactory) -> None:
    make_user("taken", email="taken@example.com")

    for kwargs in ({"crm_login": "TAKEN"}, {"crm_login": "other", "email": "Taken@Example.com"}):
        with pytest.raises(DomainError) as error:
            services.create_user(actor=SYSTEM, display_name="X", **kwargs)
        assert error.value.code == "login_or_email_taken"
    assert AuditEvent.objects.filter(action="user.created").count() == 1


@pytest.mark.parametrize("email", ["not-an-email", "a@b", "two@@example.com"])
def test_invalid_email_is_refused(email: str) -> None:
    with pytest.raises(DomainError) as error:
        services.create_user(actor=SYSTEM, crm_login="mail", display_name="M", email=email)
    assert error.value.code == "invalid_email"


def test_blank_display_name_is_refused() -> None:
    with pytest.raises(DomainError) as error:
        services.create_user(actor=SYSTEM, crm_login="noname", display_name="   ")
    assert error.value.code == "invalid_display_name"


def test_set_password_replaces_hash_and_audits_without_the_value(make_user: UserFactory) -> None:
    user = make_user(password=STRONG_PASSWORD)
    new_password = "another-long-passphrase"

    services.set_password(actor=SYSTEM, user=user, raw_password=new_password)

    user.refresh_from_db()
    assert user.check_password(new_password) is True
    assert user.check_password(STRONG_PASSWORD) is False
    event = AuditEvent.objects.get(action="user.password_changed")
    assert event.entity_id == str(user.pk)
    assert event.metadata == {}


def test_set_password_applies_the_policy(make_user: UserFactory) -> None:
    user = make_user(password=STRONG_PASSWORD)

    with pytest.raises(DomainError):
        services.set_password(actor=SYSTEM, user=user, raw_password="tooshort")

    user.refresh_from_db()
    assert user.check_password(STRONG_PASSWORD) is True
    assert not AuditEvent.objects.filter(action="user.password_changed").exists()


def test_bump_permissions_version_touches_only_named_users(make_user: UserFactory) -> None:
    first, second = make_user(), make_user()

    assert services.bump_permissions_version([first.pk]) == 1

    assert User.objects.get(pk=first.pk).permissions_version == 2
    assert User.objects.get(pk=second.pk).permissions_version == 1
    assert User.objects.filter(permissions_version=F("permissions_version")).count() == 2
