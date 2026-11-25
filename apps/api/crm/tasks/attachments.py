"""Files attached to tasks (D006, Q16, Q19, Q24, D039).

* Whoever may see the task may list and download its files; nobody else can —
  there is no address of a file that works without the task's access check.
* The assignee and the manager attach files (`task.attach`).
* The file's type is decided from its content (`crm.files.validation`).
* Names and contents of files never reach the audit log.

PROVISIONAL (docs/OPEN_QUESTIONS.md): who removes a file — the manager of the
task's department (`task.attachment.delete`), by analogy with D038. A removed
file is hidden; its bytes stay in the storage until a purge is decided (Q06).
"""

import contextlib
import hashlib
from collections.abc import Iterator
from typing import BinaryIO
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.common.ids import new_id
from crm.files import validation
from crm.files.storage import CHUNK, ObjectNotFoundError, StorageError, file_size, get_storage
from crm.tasks import policy, services
from crm.tasks.models import Attachment, Task


def _unavailable(error: Exception) -> DomainError:
    failure = DomainError("storage_unavailable", "The file storage is not available. Try later.")
    failure.__cause__ = error
    return failure


def _log(actor: Actor, action: str, attachment: Attachment, task: Task) -> None:
    audit.record(
        actor=actor,
        action=action,
        entity_type="task",
        entity_id=str(task.pk),
        metadata={
            "department_id": str(task.responsible_department_id),
            "attachment_id": str(attachment.pk),
            "byte_size": attachment.byte_size,
            "content_type": attachment.content_type,
        },
    )


def _writable_task(actor: Actor, task_id: UUID, code: str, *, lock: bool) -> Task:
    task = services._locked(actor, task_id) if lock else services.get_task(actor, task_id)
    policy.require(actor, code, task)
    services._require_editable(task)
    return task


def attachments(actor: Actor, task: Task) -> QuerySet[Attachment]:
    if not policy.allowed(actor, policy.READ, task):
        return Attachment.objects.none()
    return task.attachments.filter(deleted_at__isnull=True).select_related("uploader")


def add_attachment(*, actor: Actor, task_id: UUID, stream: BinaryIO, name: str) -> Attachment:
    """Check, store and register a file. `stream` must be seekable."""
    if actor.user is None:
        raise PermissionDeniedError()
    # Rights first: nothing is inspected or stored for somebody who may not attach.
    _writable_task(actor, task_id, "task.attach", lock=False)
    size = file_size(stream)
    if size > settings.ATTACHMENT_MAX_BYTES:
        raise DomainError("file_too_large", "The file is larger than 100 MB.")
    accepted = validation.inspect(stream, name)

    digest = hashlib.sha256()
    while chunk := stream.read(CHUNK):
        digest.update(chunk)
    stream.seek(0)

    storage = get_storage()
    attachment_id = new_id()
    key = f"attachments/{attachment_id}"
    try:
        storage.save(key, stream, content_type=accepted.content_type)
    except StorageError as error:
        raise _unavailable(error) from error
    try:
        with transaction.atomic():
            # Rights again, under the lock: they may have changed during the upload.
            task = _writable_task(actor, task_id, "task.attach", lock=True)
            attachment = Attachment.objects.create(
                id=attachment_id,
                task=task,
                uploader=actor.user,
                storage=storage.name,
                storage_key=key,
                original_name=accepted.name,
                content_type=accepted.content_type,
                byte_size=size,
                sha256=digest.hexdigest(),
            )
            _log(actor, "task.attachment_added", attachment, task)
    except BaseException:
        # No row points at the object: do not leave it behind.
        with contextlib.suppress(StorageError):
            storage.delete(key)
        raise
    return attachment


def open_attachment(
    *, actor: Actor, task_id: UUID, attachment_id: UUID
) -> tuple[Attachment, Iterator[bytes]]:
    """The file's record and its bytes, for somebody who may see the task."""
    task = services.get_task(actor, task_id)
    attachment = attachments(actor, task).filter(pk=attachment_id).first()
    if attachment is None:
        raise DomainError("attachment_not_found", "No such file.")
    try:
        return attachment, get_storage().open(attachment.storage_key)
    except ObjectNotFoundError as error:
        raise DomainError("attachment_not_found", "No such file.") from error
    except StorageError as error:
        raise _unavailable(error) from error


def delete_attachment(*, actor: Actor, task_id: UUID, attachment_id: UUID) -> None:
    with transaction.atomic():
        task = _writable_task(actor, task_id, "task.attachment.delete", lock=True)
        if actor.user is None:
            raise PermissionDeniedError()
        attachment = (
            Attachment.objects.select_for_update()
            .filter(pk=attachment_id, task=task, deleted_at__isnull=True)
            .first()
        )
        if attachment is None:
            raise DomainError("attachment_not_found", "No such file.")
        attachment.deleted_at = timezone.now()
        attachment.deleted_by = actor.user
        attachment.save(update_fields=["deleted_at", "deleted_by"])
        _log(actor, "task.attachment_deleted", attachment, task)
