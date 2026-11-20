"""Writing audit events.

Call `record` inside the transaction that performs the change, so the event and
the change commit or roll back together.
"""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from crm.audit.models import AuditEvent
from crm.common.actors import Actor

# A key containing any of these fragments may not appear in audit metadata at any depth.
_FORBIDDEN_KEY_FRAGMENTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "hash",
    "otp",
    "credential",
    "cookie",
    "authorization",
)


class UnsafeAuditMetadataError(ValueError):
    """Audit metadata looked like it carries a secret. This is a programming error."""


def _assert_safe(value: Any, path: str = "metadata") -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            lowered = str(key).lower()
            if lowered.startswith(("has_", "is_")):
                # Boolean facts such as `has_password` describe state, not the secret.
                if not isinstance(nested, bool):
                    raise UnsafeAuditMetadataError(f"{path}.{key} must be a boolean.")
                continue
            if any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS):
                raise UnsafeAuditMetadataError(
                    f"{path}.{key} must not be written to the audit log."
                )
            _assert_safe(nested, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, nested in enumerate(value):
            _assert_safe(nested, f"{path}[{index}]")


def record(
    *,
    actor: Actor,
    action: str,
    entity_type: str,
    entity_id: str,
    metadata: Mapping[str, Any] | None = None,
    correlation_id: UUID | None = None,
) -> AuditEvent:
    data = dict(metadata or {})
    _assert_safe(data)
    return AuditEvent.objects.create(
        actor_type=actor.type.value,
        actor=actor.user,
        actor_label=actor.label,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata=data,
        correlation_id=correlation_id,
    )
