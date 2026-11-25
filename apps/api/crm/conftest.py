"""Shared fixtures for backend tests."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from pytest_django.fixtures import Settings as SettingsWrapper

from crm.celery import app as celery_app
from crm.common.actors import Actor
from crm.identity import enrollment, setup
from crm.identity import services as identity
from crm.identity.models import User
from crm.telegram.fake import FakeGateway

STRONG_PASSWORD = "plum-orbit-candle-73"

UserFactory = Callable[..., User]


@pytest.fixture
def make_user(db: None) -> UserFactory:
    counter = 0

    def factory(login: str | None = None, **kwargs: object) -> User:
        nonlocal counter
        counter += 1
        return identity.create_user(
            actor=Actor.system("tests"),
            crm_login=login or f"user{counter}",
            display_name=str(kwargs.pop("display_name", f"User {counter}")),
            **kwargs,  # type: ignore[arg-type]
        )

    return factory


@pytest.fixture
def administrator(db: None) -> User:
    user, _token = setup.create_first_administrator(
        operator="os:tests", crm_login="root.admin", display_name="Admin", password=STRONG_PASSWORD
    )
    return user


@pytest.fixture
def admin_actor(administrator: User) -> Actor:
    return Actor.for_user(administrator)


@pytest.fixture(autouse=True)
def fake_telegram(settings: SettingsWrapper) -> Iterator[type[FakeGateway]]:
    """No test talks to Telegram or to the task queue."""
    settings.TELEGRAM_GATEWAY = "crm.telegram.fake.FakeGateway"
    FakeGateway.clear()
    celery_app.conf.task_always_eager = True
    try:
        yield FakeGateway
    finally:
        celery_app.conf.task_always_eager = False
        FakeGateway.clear()


@dataclass(frozen=True)
class Employee:
    user: User
    password: str
    telegram_user_id: int


EmployeeFactory = Callable[..., Employee]


@pytest.fixture
def make_employee(make_user: UserFactory, admin_actor: Actor) -> EmployeeFactory:
    """An active account with a password and a bound Telegram account, created
    through the real enrollment flow."""
    counter = 0

    def factory(login: str | None = None, *, telegram_user_id: int | None = None) -> Employee:
        nonlocal counter
        counter += 1
        user = make_user(login, password=STRONG_PASSWORD)
        telegram_id = telegram_user_id or 700_000 + counter
        token = enrollment.issue_token(actor=admin_actor, user=user)
        enrollment.redeem_token(
            raw_token=token.value,
            telegram_user_id=telegram_id,
            telegram_username=None,
            chat_is_private=True,
        )
        user.refresh_from_db()
        return Employee(user=user, password=STRONG_PASSWORD, telegram_user_id=telegram_id)

    return factory


@pytest.fixture
def employee(make_employee: EmployeeFactory) -> Employee:
    return make_employee("anna.petrova")
