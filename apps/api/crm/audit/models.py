from typing import Any, NoReturn

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now

from crm.common.actors import ActorType
from crm.common.ids import new_id


class AppendOnlyError(RuntimeError):
    """Raised when code tries to change or remove an audit event."""


class AuditEventQuerySet(models.QuerySet["AuditEvent"]):
    def update(self, **kwargs: Any) -> NoReturn:
        raise AppendOnlyError("Audit events cannot be updated.")

    def delete(self) -> NoReturn:
        raise AppendOnlyError("Audit events cannot be deleted.")


class AuditEvent(models.Model):
    """One fact about a change, written in the same transaction as the change.

    Append-only: the model refuses updates and deletes, and a database trigger
    enforces the same for any other client (see migration 0002). Retention is
    indefinite; removal is possible only through the explicit cleanup procedure (Q14).
    """

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    occurred_at = models.DateTimeField(db_default=Now())

    actor_type = models.CharField(max_length=16, choices=[(t.value, t.value) for t in ActorType])
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )
    # For system and CLI actors: the component or operating-system account.
    actor_label = models.CharField(max_length=150, blank=True)

    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=64)
    entity_id = models.CharField(max_length=64)
    # Safe facts only: never passwords, tokens, hashes or form contents.
    metadata = models.JSONField(default=dict)
    correlation_id = models.UUIDField(null=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        db_table = "audit_event"
        indexes = [
            models.Index(
                fields=["entity_type", "entity_id", "occurred_at"], name="audit_entity_idx"
            ),
            models.Index(fields=["actor", "occurred_at"], name="audit_actor_idx"),
            models.Index(fields=["action", "occurred_at"], name="audit_action_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(actor_type=ActorType.USER.value, actor__isnull=False)
                    | (~Q(actor_type=ActorType.USER.value) & Q(actor__isnull=True))
                ),
                name="audit_event_actor_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.entity_type}:{self.entity_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyError("Audit events cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise AppendOnlyError("Audit events cannot be deleted.")
