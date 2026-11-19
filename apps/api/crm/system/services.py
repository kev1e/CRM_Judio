"""Domain services of the technical module.

Views and Celery tasks call these functions; they do not touch the ORM themselves.
"""

import logging
import re
from dataclasses import dataclass

import redis
from django.conf import settings
from django.db import DatabaseError, connection, transaction
from django.db.models import F
from django.utils import timezone

from crm.system.models import Heartbeat

logger = logging.getLogger(__name__)

_COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_REDIS_TIMEOUT_SECONDS = 1.0


@dataclass(frozen=True, slots=True)
class Readiness:
    database: bool
    redis: bool

    @property
    def ready(self) -> bool:
        return self.database and self.redis


def check_database() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        logger.warning("Readiness: database check failed", exc_info=True)
        return False
    return True


def check_redis() -> bool:
    client = redis.Redis.from_url(
        settings.REDIS_URL,
        socket_connect_timeout=_REDIS_TIMEOUT_SECONDS,
        socket_timeout=_REDIS_TIMEOUT_SECONDS,
    )
    try:
        return bool(client.ping())
    except redis.RedisError:
        logger.warning("Readiness: Redis check failed", exc_info=True)
        return False
    finally:
        client.close()


def get_readiness() -> Readiness:
    return Readiness(database=check_database(), redis=check_redis())


def record_heartbeat(component: str) -> Heartbeat:
    """Register one beat of `component`, creating its row on the first beat."""
    if not _COMPONENT_RE.fullmatch(component):
        raise ValueError("Invalid component name.")

    now = timezone.now()
    with transaction.atomic():
        heartbeat, created = Heartbeat.objects.select_for_update().get_or_create(
            component=component,
            defaults={"beats": 1, "last_beat_at": now},
        )
        if not created:
            Heartbeat.objects.filter(pk=heartbeat.pk).update(beats=F("beats") + 1, last_beat_at=now)
            heartbeat.refresh_from_db()
    return heartbeat
