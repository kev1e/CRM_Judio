"""Making a request by a template and reading what was typed (S5; D009, Q21, D040).

* D040: a request is submitted by whoever may create tasks for the department —
  the department's manager. The template must be available in that department.
* The form is always the latest published version; the request keeps pointing
  at exactly that version, whatever is published later (D009).
* Values are checked here, on the server (`crm.request_templates.values`); the
  website and Telegram both call `submit`.
* The typed values are shown to whoever may read the task and to nobody else
  (D003). Nothing of them reaches the audit log.

PROVISIONAL (docs/OPEN_QUESTIONS.md): the files of a form come with the right to
create the request (no separate `task.attach` is asked for); all files of one
request together fit the limit of one attachment (100 MB).
"""

import contextlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, BinaryIO
from uuid import UUID

from django.db import transaction

from crm.access import services as access
from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.identity.models import User
from crm.organization.models import Department
from crm.request_templates import services, values
from crm.request_templates.models import (
    RequestTemplate,
    Submission,
    SubmissionSource,
    TemplateDepartment,
    TemplateVersion,
)
from crm.tasks import attachments
from crm.tasks import services as tasks
from crm.tasks.models import Attachment, Priority, Task, TaskType

CREATE = "task.create"


@dataclass(frozen=True)
class Offer:
    """A form somebody may fill in now, and the departments they may fill it in for."""

    template: RequestTemplate
    version: TemplateVersion
    departments: list[Department]


@dataclass(frozen=True)
class Answer:
    """One field of a submitted form, ready to be shown."""

    key: str
    question: str
    type: str
    filled: bool
    value: Any = None
    currency: str | None = None
    with_time: bool = False
    attachment_id: UUID | None = None


@dataclass(frozen=True)
class SubmittedForm:
    template_name: str
    version: int
    answers: list[Answer]


def _not_found() -> DomainError:
    # The same answer for a template that does not exist, is retired, has no
    # published version or is not available in the department.
    return DomainError("template_not_found", "No such request form.")


def offers(actor: Actor) -> list[Offer]:
    """Forms the actor may submit right now. Empty for everybody who creates no
    tasks: an employee, the administrator, the superuser (D040)."""
    scope = access.department_scope(actor, CREATE)
    result = []
    for template in services.usable_templates(actor).prefetch_related("departments"):
        departments = sorted(
            (
                department
                for department in template.departments.all()
                if department.is_active and scope.covers(department.pk)
            ),
            key=lambda department: department.name,
        )
        version = services.latest_version(template)
        if departments and version is not None:
            result.append(Offer(template, version, departments))
    return result


def _usable(template_id: UUID, department_id: UUID, *, lock: bool) -> TemplateVersion:
    templates = RequestTemplate.objects.filter(pk=template_id, is_active=True)
    template = (templates.select_for_update() if lock else templates).first()
    if (
        template is None
        or not TemplateDepartment.objects.filter(
            template=template, department_id=department_id, department__is_active=True
        ).exists()
    ):
        raise _not_found()
    version = services.latest_version(template)
    if version is None:
        raise _not_found()
    return version


def submit(
    *,
    actor: Actor,
    template_id: UUID,
    version: int,
    department_id: UUID,
    assignee_id: UUID,
    title: str,
    form_values: Any,
    files: Mapping[str, tuple[BinaryIO, str]] | None = None,
    priority: str = Priority.NORMAL,
    due_at: datetime | None = None,
    source: str = SubmissionSource.WEB,
) -> Task:
    """Create a request from a filled form. All of it or none of it."""
    # D040: the right to create tasks for this department comes first — nothing
    # about templates is revealed to somebody who has it not.
    access.require_in_department(actor, CREATE, department_id)
    if actor.user is None:
        raise PermissionDeniedError()
    if source not in SubmissionSource.values:
        raise DomainError("invalid_source", "Unknown source of a request.")
    files = files or {}

    def current() -> TemplateVersion:
        latest = _usable(
            template_id, department_id, lock=transaction.get_connection().in_atomic_block
        )
        if latest.number != version:
            raise DomainError(
                "template_changed", "The form has changed. Open it again and fill it in anew."
            )
        return latest

    published = current()
    people = set(tasks.eligible_assignees(actor, department_id).values_list("pk", flat=True))
    clean = values.clean_values(published.fields, form_values, file_keys=set(files), people=people)
    # Every file is checked before anything is created or stored.
    file_fields = [field["key"] for field in published.fields if field["key"] in files]
    checked = []
    for key in file_fields:
        stream, name = files[key]
        try:
            checked.append(attachments.check_file(stream, name))
        except DomainError as error:
            if error.code in ("file_too_large", "storage_unavailable"):
                raise
            raise DomainError(error.code, error.message, {"field": key}) from error

    stored_keys: list[str] = []
    try:
        with transaction.atomic():
            # Again under a lock: the template may have been retired or
            # republished while the files were being read.
            published = current()
            task = tasks.create_task(
                actor=actor,
                title=title,
                department_id=department_id,
                assignee_id=assignee_id,
                priority=priority,
                due_at=due_at,
                task_type=TaskType.REQUEST,
                checkpoints=published.checkpoints,
            )
            added = attachments.attach_to_new_task(
                actor=actor, task=task, files=checked, stored_keys=stored_keys
            )
            for key, attachment in zip(file_fields, added, strict=True):
                clean[key] = str(attachment.pk)
            Submission.objects.create(task=task, version=published, values=clean, source=source)
            audit.record(
                actor=actor,
                action="request.submitted",
                entity_type="task",
                entity_id=str(task.pk),
                metadata={
                    "department_id": str(department_id),
                    "template_id": str(published.template_id),
                    "version_id": str(published.pk),
                    "version": published.number,
                    "source": source,
                    # How much was filled in, never what.
                    "filled_fields": len(clean),
                    "files": len(added),
                },
            )
    except BaseException:
        attachments.discard(stored_keys)
        raise
    return task


def submitted_form(actor: Actor, task_id: UUID) -> SubmittedForm | None:
    """The form a request was made with and its values — for whoever may read
    the task (`tasks.get_task` refuses everybody else). None for a task made
    without a form."""
    task = tasks.get_task(actor, task_id)
    submission = Submission.objects.select_related("version__template").filter(task=task).first()
    if submission is None:
        return None
    fields: list[dict[str, Any]] = submission.version.fields
    stored: dict[str, Any] = submission.values

    def identifiers(kind: str) -> list[UUID]:
        found = []
        for field in fields:
            if field["type"] == kind and field["key"] in stored:
                with contextlib.suppress(ValueError, TypeError):
                    found.append(UUID(stored[field["key"]]))
        return found

    # Names of people stay readable after they leave the department or the company.
    names = dict(
        User.objects.filter(pk__in=identifiers("employee")).values_list("pk", "display_name")
    )
    live_files = {
        attachment.pk: attachment
        for attachment in Attachment.objects.filter(
            task=task, pk__in=identifiers("file"), deleted_at__isnull=True
        )
    }

    answers = []
    for field in fields:
        key, kind = field["key"], field["type"]
        base = {"key": key, "question": field["label"], "type": kind}
        if key not in stored:
            answers.append(Answer(**base, filled=False))
            continue
        value = stored[key]
        if kind == "employee":
            answers.append(Answer(**base, filled=True, value=names.get(UUID(value))))
        elif kind == "file":
            attachment = live_files.get(UUID(value))
            # A removed file stays "filled": something was attached, it is gone.
            answers.append(
                Answer(
                    **base,
                    filled=True,
                    value=attachment.original_name if attachment else None,
                    attachment_id=attachment.pk if attachment else None,
                )
            )
        elif kind == "select":
            answers.append(
                Answer(**base, filled=True, value=value if isinstance(value, list) else [value])
            )
        else:
            answers.append(
                Answer(
                    **base,
                    filled=True,
                    value=value,
                    currency=field.get("currency"),
                    with_time=bool(field.get("with_time")),
                )
            )
    return SubmittedForm(
        template_name=submission.version.template.name,
        version=submission.version.number,
        answers=answers,
    )
