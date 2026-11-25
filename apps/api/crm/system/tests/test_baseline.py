"""Guards of the platform baseline: what must never appear, and what must stay in sync."""

import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import Client

API_DIR = Path(settings.BASE_DIR)
COMMITTED_SCHEMA = API_DIR.parent.parent / "packages" / "contracts" / "openapi.yaml"


@pytest.mark.django_db
def test_schema_contains_only_own_tables() -> None:
    # D032: no auth_*, django_admin_log, django_session or django_content_type tables.
    assert sorted(connection.introspection.table_names()) == [
        "access_role",
        "access_role_grant",
        "access_user_role",
        "audit_event",
        "django_migrations",
        "identity_login_challenge",
        "identity_password_setup_token",
        "identity_session",
        "identity_telegram_enrollment_token",
        "identity_throttle_counter",
        "identity_user",
        "organization_department",
        "organization_department_manager",
        "organization_department_membership",
        "system_heartbeat",
        "tasks_checkpoint",
        "tasks_status",
        "tasks_status_transition",
        "tasks_task",
    ]


def test_django_auth_admin_sessions_and_contenttypes_are_not_installed() -> None:
    forbidden = {
        "django.contrib.auth",
        "django.contrib.admin",
        "django.contrib.sessions",
        "django.contrib.contenttypes",
    }
    assert forbidden.isdisjoint(settings.INSTALLED_APPS)
    assert settings.AUTH_USER_MODEL == "identity.User"


@pytest.mark.parametrize("path", ["/admin", "/admin/", "/admin/login/", "/api/admin/"])
def test_admin_route_does_not_exist(path: str) -> None:
    # D032-B1, requirement 6.
    response = Client().get(path)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.django_db
def test_models_have_no_missing_migrations() -> None:
    call_command("makemigrations", check=True, dry_run=True, verbosity=0)


def test_committed_openapi_schema_matches_the_code(tmp_path: Path) -> None:
    generated = tmp_path / "openapi.yaml"
    call_command("spectacular", file=str(generated), validate=True, fail_on_warn=True)

    assert generated.read_text() == COMMITTED_SCHEMA.read_text(), (
        "OpenAPI schema changed: run `pnpm contracts:export && pnpm contracts:generate` "
        "and commit packages/contracts."
    )


def _start_django(env_overrides: dict[str, str | None]) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/bin:/bin",
        "CRM_ENV_FILE": "",  # ignore the developer's .env
        "DJANGO_SETTINGS_MODULE": "crm.settings",
        "DJANGO_SECRET_KEY": "k" * 64,
        "DJANGO_ALLOWED_HOSTS": "localhost",
        "DATABASE_URL": "postgres://u:p@127.0.0.1:5432/db",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
    }
    for key, value in env_overrides.items():
        if value is None:
            env.pop(key)
        else:
            env[key] = value
    return subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        cwd=API_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_django_starts_with_complete_environment() -> None:
    assert _start_django({}).returncode == 0


@pytest.mark.parametrize(
    "variable", ["DJANGO_SECRET_KEY", "DJANGO_ALLOWED_HOSTS", "DATABASE_URL", "REDIS_URL"]
)
def test_missing_required_variable_stops_startup(variable: str) -> None:
    result = _start_django({variable: None})

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert variable in result.stderr


@pytest.mark.parametrize("secret", ["change-me-generate-a-long-random-string" + "x" * 30, "short"])
def test_placeholder_or_weak_secret_key_stops_startup(secret: str) -> None:
    result = _start_django({"DJANGO_SECRET_KEY": secret})

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY must be a random string" in result.stderr


def test_non_postgres_database_is_rejected() -> None:
    result = _start_django({"DATABASE_URL": "sqlite:///tmp/x.sqlite3"})

    assert result.returncode != 0
    assert "must point to PostgreSQL" in result.stderr
