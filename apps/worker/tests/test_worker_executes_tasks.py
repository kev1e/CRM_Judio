"""End-to-end check of the worker: a real `celery worker` process, real Redis, real PostgreSQL."""

import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Callable, Iterator
from urllib.parse import quote

import pytest
import redis
from django.conf import settings
from django.db import connection

from crm.celery import app
from crm.system.models import Heartbeat
from crm.system.tasks import record_heartbeat
from crm_worker.app import app as worker_app

# Real transactions, because the worker is another process. `serialized_rollback`
# restores the rows created by data migrations (system roles) after each test.
pytestmark = pytest.mark.django_db(transaction=True, serialized_rollback=True)

STARTUP_TIMEOUT_SECONDS = 60
TASK_TIMEOUT_SECONDS = 30
SETTLE_SECONDS = 1.5


def _wait_until(predicate: Callable[[], bool], timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.2)
    pytest.fail(f"Timed out after {timeout}s waiting for {what}")


def _test_database_url() -> str:
    db = connection.settings_dict
    return (
        f"postgres://{quote(db['USER'], safe='')}:{quote(db['PASSWORD'], safe='')}"
        f"@{db['HOST']}:{db['PORT']}/{quote(db['NAME'], safe='')}"
    )


@pytest.fixture
def queue() -> Iterator[str]:
    name = f"test-{uuid.uuid4().hex}"
    yield name
    client = redis.Redis.from_url(settings.CELERY_BROKER_URL)
    try:
        client.delete(name)
    finally:
        client.close()


@pytest.fixture
def worker(queue: str) -> Iterator[str]:
    node = f"test-{uuid.uuid4().hex[:8]}@{socket.gethostname()}"
    env = {**os.environ, "DATABASE_URL": _test_database_url(), "CRM_ENV_FILE": ""}
    env.setdefault("DJANGO_SECRET_KEY", str(settings.SECRET_KEY))
    env.setdefault("DJANGO_ALLOWED_HOSTS", ",".join(settings.ALLOWED_HOSTS))
    env.setdefault("REDIS_URL", settings.REDIS_URL)
    process = subprocess.Popen(
        [
            sys.executable, "-m", "celery", "-A", "crm_worker.app", "worker",
            "--queues", queue, "--hostname", node,
            "--pool", "prefork", "--concurrency", "2", "--loglevel", "WARNING",
            "--without-gossip", "--without-mingle",
        ],
        env=env,
    )  # fmt: skip
    try:
        _wait_until(
            lambda: bool(app.control.inspect(destination=[node], timeout=1).ping()),
            STARTUP_TIMEOUT_SECONDS,
            "the Celery worker to start",
        )
        yield node
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


def _beats(component: str) -> int:
    row = Heartbeat.objects.filter(component=component).first()
    return row.beats if row else 0


def test_worker_app_is_the_shared_celery_app() -> None:
    assert worker_app is app
    assert "system.record_heartbeat" in app.tasks


def test_worker_executes_each_enqueued_task_exactly_once(worker: str, queue: str) -> None:
    component = "worker-e2e"

    record_heartbeat.apply_async(args=(component,), queue=queue)
    _wait_until(lambda: _beats(component) >= 1, TASK_TIMEOUT_SECONDS, "the first task")
    time.sleep(SETTLE_SECONDS)
    assert _beats(component) == 1

    for _ in range(5):
        record_heartbeat.apply_async(args=(component,), queue=queue)
    _wait_until(lambda: _beats(component) >= 6, TASK_TIMEOUT_SECONDS, "five more tasks")
    time.sleep(SETTLE_SECONDS)
    assert _beats(component) == 6


def test_invalid_task_argument_does_not_write_or_kill_the_worker(worker: str, queue: str) -> None:
    record_heartbeat.apply_async(args=("Not Valid",), queue=queue)
    record_heartbeat.apply_async(args=("after-bad-task",), queue=queue)

    _wait_until(lambda: _beats("after-bad-task") == 1, TASK_TIMEOUT_SECONDS, "the follow-up task")
    assert Heartbeat.objects.count() == 1
