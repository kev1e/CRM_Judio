"""Shared fixtures for backend tests."""

from collections.abc import Callable

import pytest

from crm.common.actors import Actor
from crm.identity import services as identity
from crm.identity import setup
from crm.identity.models import User

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
