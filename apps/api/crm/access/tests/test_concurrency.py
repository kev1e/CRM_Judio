"""Races that must not leave the installation with two "first" administrators or none."""

import threading
from collections.abc import Callable

import pytest
from django.db import connection

from crm.access import services
from crm.access.models import Role, UserRole
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.conftest import STRONG_PASSWORD
from crm.identity.models import User

# Real transactions and separate connections are required for the row locks to matter.
pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)


def _run_together(*operations: Callable[[], object]) -> list[object]:
    barrier = threading.Barrier(len(operations))
    results: list[object] = [None] * len(operations)

    def worker(index: int, operation: Callable[[], object]) -> None:
        try:
            barrier.wait(timeout=10)
            results[index] = operation()
        except Exception as exc:
            results[index] = exc
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(index, operation))
        for index, operation in enumerate(operations)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def test_only_one_of_two_simultaneous_first_administrators_is_created() -> None:
    def create(login: str) -> Callable[[], object]:
        return lambda: services.create_first_administrator(
            operator="os:tests", crm_login=login, display_name=login, password=STRONG_PASSWORD
        )

    results = _run_together(create("first.admin"), create("second.admin"))

    created = [r for r in results if isinstance(r, User)]
    refused = [r for r in results if isinstance(r, DomainError)]
    assert len(created) == 1, results
    assert len(refused) == 1, results
    assert refused[0].code == "administrator_exists"
    assert User.objects.count() == 1
    assert UserRole.objects.filter(role__key="administrator").count() == 1


def test_two_administrators_cannot_remove_each_other_at_the_same_time() -> None:
    first = services.create_first_administrator(
        operator="os:tests", crm_login="first.admin", display_name="A", password=STRONG_PASSWORD
    )
    role = Role.objects.get(key="administrator")
    second = User.objects.create(crm_login="second.admin", display_name="B")
    services.assign_role(actor=Actor.for_user(first), user=second, role=role)

    results = _run_together(
        lambda: services.revoke_role(actor=Actor.for_user(first), user=second, role=role),
        lambda: services.revoke_role(actor=Actor.for_user(second), user=first, role=role),
    )

    # Whichever request wins, exactly one administrator must remain, and the loser
    # is refused because by then it is no longer an administrator itself.
    assert results.count(True) == 1, results
    (failure,) = [r for r in results if r is not True]
    assert isinstance(failure, PermissionDeniedError), results
    assert UserRole.objects.filter(role=role, user__is_active=True).count() == 1
