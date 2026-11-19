import pytest
from django.db import IntegrityError, transaction

from crm.system import services, tasks
from crm.system.models import Heartbeat

pytestmark = pytest.mark.django_db


def test_first_beat_creates_row_and_next_beats_increment_it() -> None:
    first = services.record_heartbeat("worker")
    second = services.record_heartbeat("worker")

    assert first.beats == 1
    assert second.beats == 2
    assert second.last_beat_at >= first.last_beat_at
    assert Heartbeat.objects.count() == 1


def test_components_are_counted_separately() -> None:
    services.record_heartbeat("worker")
    services.record_heartbeat("scheduler")

    assert set(Heartbeat.objects.values_list("component", "beats")) == {
        ("worker", 1),
        ("scheduler", 1),
    }


@pytest.mark.parametrize("name", ["", "Worker", "has space", "-leading", "x" * 65, "a;drop"])
def test_invalid_component_name_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="Invalid component name"):
        services.record_heartbeat(name)

    assert Heartbeat.objects.count() == 0


def test_database_constraint_rejects_invalid_component_even_without_service() -> None:
    from django.utils import timezone

    with pytest.raises(IntegrityError), transaction.atomic():
        Heartbeat.objects.create(component="Not Valid", beats=1, last_beat_at=timezone.now())


def test_task_delegates_to_service() -> None:
    tasks.record_heartbeat("worker")

    assert Heartbeat.objects.get(component="worker").beats == 1
