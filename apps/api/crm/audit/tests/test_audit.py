import uuid

import pytest
from django.db import DatabaseError, connection, transaction

from crm.audit import services
from crm.audit.models import AppendOnlyError, AuditEvent
from crm.common.actors import Actor, ActorType
from crm.conftest import UserFactory

pytestmark = pytest.mark.django_db

SYSTEM = Actor.system("tests")


def _event(**overrides: object) -> AuditEvent:
    params: dict[str, object] = {
        "actor": SYSTEM,
        "action": "thing.changed",
        "entity_type": "thing",
        "entity_id": "42",
    }
    params.update(overrides)
    return services.record(**params)  # type: ignore[arg-type]


def test_record_stores_actor_action_entity_and_database_time(make_user: UserFactory) -> None:
    user = make_user()
    correlation = uuid.uuid4()

    event = _event(
        actor=Actor.for_user(user), metadata={"before": 1, "after": 2}, correlation_id=correlation
    )

    stored = AuditEvent.objects.get(pk=event.pk)
    assert stored.actor_type == "user"
    assert stored.actor == user
    assert stored.action == "thing.changed"
    assert (stored.entity_type, stored.entity_id) == ("thing", "42")
    assert stored.metadata == {"before": 1, "after": 2}
    assert stored.correlation_id == correlation
    assert stored.occurred_at is not None


def test_system_and_cli_actors_are_recorded_by_label() -> None:
    cli = _event(actor=Actor.cli("os:deploy"))

    assert (cli.actor_type, cli.actor, cli.actor_label) == ("cli", None, "os:deploy")


def test_actor_must_be_well_formed(make_user: UserFactory) -> None:
    with pytest.raises(ValueError, match="needs a user"):
        Actor(type=ActorType.USER)
    with pytest.raises(ValueError, match="needs a user"):
        Actor(type=ActorType.SYSTEM, user=make_user(), label="x")
    with pytest.raises(ValueError, match="need a label"):
        Actor(type=ActorType.CLI)


@pytest.mark.parametrize(
    "metadata",
    [
        {"password": "x"},
        {"new_password_hash": "x"},
        {"nested": {"binding_token": "x"}},
        {"list": [{"session_cookie": "x"}]},
        {"Authorization": "Bearer x"},
        {"client_secret": "x"},
        {"has_password": "yes-it-is-hunter2"},
    ],
)
def test_metadata_that_looks_like_a_secret_is_refused(metadata: dict[str, object]) -> None:
    with pytest.raises(services.UnsafeAuditMetadataError):
        _event(metadata=metadata)

    assert not AuditEvent.objects.exists()


def test_boolean_facts_about_secrets_are_allowed() -> None:
    event = _event(metadata={"has_password": True, "is_token_bound": False})

    assert event.metadata == {"has_password": True, "is_token_bound": False}


def test_model_refuses_update_and_delete() -> None:
    event = _event()

    event.action = "tampered"
    with pytest.raises(AppendOnlyError):
        event.save()
    with pytest.raises(AppendOnlyError):
        event.delete()
    with pytest.raises(AppendOnlyError):
        AuditEvent.objects.filter(pk=event.pk).update(action="tampered")
    with pytest.raises(AppendOnlyError):
        AuditEvent.objects.all().delete()

    assert AuditEvent.objects.get(pk=event.pk).action == "thing.changed"


def _execute(*statements: str) -> int:
    """Run raw SQL in one transaction, the way a client bypassing the ORM would."""
    with transaction.atomic(), connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)
        return int(cursor.rowcount)


@pytest.mark.parametrize(
    "sql",
    ["UPDATE audit_event SET action = 'tampered'", "DELETE FROM audit_event"],
)
def test_database_refuses_update_and_delete_even_for_raw_sql(sql: str) -> None:
    _event()

    with pytest.raises(DatabaseError, match="append-only"):
        _execute(sql)

    assert AuditEvent.objects.get().action == "thing.changed"


# A real transaction is needed here: inside the usual test transaction `SET LOCAL`
# would stay in force until the end of the test and hide exactly what is checked.
@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_cleanup_switch_allows_delete_only_inside_its_transaction() -> None:
    _event()

    assert _execute("SET LOCAL crm.audit_cleanup = 'on'", "DELETE FROM audit_event") == 1

    _event()
    with pytest.raises(DatabaseError, match="append-only"):
        _execute("DELETE FROM audit_event")


def test_cleanup_switch_never_allows_update() -> None:
    _event()

    with pytest.raises(DatabaseError, match="append-only"):
        _execute("SET LOCAL crm.audit_cleanup = 'on'", "UPDATE audit_event SET action = 'tampered'")


def test_event_rolls_back_with_the_change_it_describes() -> None:
    class BoomError(Exception):
        pass

    def change_that_fails() -> None:
        with transaction.atomic():
            _event()
            raise BoomError

    with pytest.raises(BoomError):
        change_that_fails()

    assert not AuditEvent.objects.exists()
