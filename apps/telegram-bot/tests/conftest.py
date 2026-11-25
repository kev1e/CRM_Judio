import pytest
from django.conf import settings

from crm.conftest import (  # noqa: F401 - shared fixtures of the API test suite
    admin_actor,
    administrator,
    employee,
    fake_telegram,
    make_employee,
    make_user,
)


@pytest.fixture(scope="session")
def django_db_modify_db_settings() -> None:
    """Use a database of its own, so the API, worker and bot suites can run at the same time."""
    default = settings.DATABASES["default"]
    default.setdefault("TEST", {})["NAME"] = f"test_{default['NAME']}_bot"
