import pytest
from django.conf import settings


@pytest.fixture(scope="session")
def django_db_modify_db_settings() -> None:
    """Use a database of its own, so API and worker suites can run at the same time."""
    default = settings.DATABASES["default"]
    default.setdefault("TEST", {})["NAME"] = f"test_{default['NAME']}_worker"
