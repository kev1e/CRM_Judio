"""Request templates: the administrator's side (S5; D009, Q21, D040).

* Only `template.manage` (the administrator) creates, edits, publishes and
  retires templates and changes the departments they are available in.
* Editing changes a draft. Publishing copies the draft into a new immutable
  version; earlier versions and the requests made with them are untouched.
* A template is available only in the departments listed for it; with no
  department listed it is available to nobody (deny by default).
* D040: requests are submitted by managers. A template is offered to a manager
  for the departments they manage that are on the template's list.

Managing templates shows no task and no request (D003).
"""

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Max, QuerySet

from crm.access import services as access
from crm.access.permissions import Scope
from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.organization.models import Department
from crm.request_templates import schema
from crm.request_templates.models import RequestTemplate, TemplateDepartment, TemplateVersion

MANAGE = "template.manage"


def _require_manage(actor: Actor) -> None:
    access.require_permission(actor, MANAGE, at_least=Scope.COMPANY)


def _log(actor: Actor, action: str, template: RequestTemplate, **metadata: object) -> None:
    audit.record(
        actor=actor,
        action=action,
        entity_type="request_template",
        entity_id=str(template.pk),
        metadata={"name": template.name, **metadata},
    )


def _clean_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name or len(name) > 150:
        raise DomainError(
            "invalid_template_name", "A template needs a name of up to 150 characters."
        )
    return name


def _locked(template_id: UUID) -> RequestTemplate:
    template = RequestTemplate.objects.select_for_update().filter(pk=template_id).first()
    if template is None:
        raise DomainError("template_not_found", "No such template.")
    return template


# --- Reading ----------------------------------------------------------------


def all_templates(*, actor: Actor) -> QuerySet[RequestTemplate]:
    _require_manage(actor)
    return RequestTemplate.objects.prefetch_related("departments", "versions")


def latest_version(template: RequestTemplate) -> TemplateVersion | None:
    return template.versions.order_by("-number").first()


# --- Editing the draft ------------------------------------------------------


def create_template(*, actor: Actor, name: str, description: str = "") -> RequestTemplate:
    _require_manage(actor)
    if actor.user is None:
        raise PermissionDeniedError()
    clean = _clean_name(name)
    try:
        with transaction.atomic():
            template = RequestTemplate.objects.create(
                name=clean, description=description.strip()[:500], created_by=actor.user
            )
            _log(actor, "request_template.created", template)
    except IntegrityError as error:
        raise DomainError(
            "template_name_taken", "A template with this name already exists."
        ) from error
    return template


def update_template(
    *,
    actor: Actor,
    template_id: UUID,
    name: str | None = None,
    description: str | None = None,
    fields: Any = None,
    checkpoints: Any = None,
) -> RequestTemplate:
    """Change the name, the description or the draft of the form. Nothing that
    is already published changes."""
    _require_manage(actor)
    clean_fields = schema.clean_fields(fields) if fields is not None else None
    clean_checkpoints = schema.clean_checkpoints(checkpoints) if checkpoints is not None else None
    try:
        with transaction.atomic():
            template = _locked(template_id)
            changed: list[str] = []
            if name is not None and (clean := _clean_name(name)) != template.name:
                template.name = clean
                changed.append("name")
            if description is not None and description.strip()[:500] != template.description:
                template.description = description.strip()[:500]
                changed.append("description")
            if clean_fields is not None and clean_fields != template.draft_fields:
                template.draft_fields = clean_fields
                changed.append("draft_fields")
            if clean_checkpoints is not None and clean_checkpoints != template.draft_checkpoints:
                template.draft_checkpoints = clean_checkpoints
                changed.append("draft_checkpoints")
            if changed:
                if {"draft_fields", "draft_checkpoints"} & set(changed):
                    template.has_unpublished_changes = True
                    changed.append("has_unpublished_changes")
                template.save(update_fields=[*changed, "updated_at"])
                # Which parts changed, not the form's contents.
                _log(
                    actor,
                    "request_template.updated",
                    template,
                    changed=sorted(set(changed) - {"has_unpublished_changes"}),
                )
    except IntegrityError as error:
        raise DomainError(
            "template_name_taken", "A template with this name already exists."
        ) from error
    return template


def set_departments(
    *, actor: Actor, template_id: UUID, department_ids: Iterable[UUID]
) -> RequestTemplate:
    """Replace the list of departments the template is available in (Q21).
    Takes effect at once, for every published version."""
    _require_manage(actor)
    wanted = set(department_ids)
    with transaction.atomic():
        template = _locked(template_id)
        known = set(
            Department.objects.filter(pk__in=wanted, is_active=True).values_list("pk", flat=True)
        )
        if known != wanted:
            raise DomainError("department_not_found", "No such open department.")
        current = set(
            TemplateDepartment.objects.filter(template=template).values_list(
                "department_id", flat=True
            )
        )
        if wanted != current:
            TemplateDepartment.objects.filter(
                template=template, department_id__in=current - wanted
            ).delete()
            TemplateDepartment.objects.bulk_create(
                TemplateDepartment(template=template, department_id=pk) for pk in wanted - current
            )
            _log(
                actor,
                "request_template.departments_changed",
                template,
                added=sorted(str(pk) for pk in wanted - current),
                removed=sorted(str(pk) for pk in current - wanted),
            )
    return template


def set_active(*, actor: Actor, template_id: UUID, active: bool) -> RequestTemplate:
    """Retire a template or bring it back. Requests already made are untouched."""
    _require_manage(actor)
    with transaction.atomic():
        template = _locked(template_id)
        if template.is_active != active:
            template.is_active = active
            template.save(update_fields=["is_active", "updated_at"])
            _log(
                actor,
                "request_template.restored" if active else "request_template.retired",
                template,
            )
    return template


# --- Publishing -------------------------------------------------------------


def publish(*, actor: Actor, template_id: UUID) -> TemplateVersion:
    """Turn the draft into the next immutable version."""
    _require_manage(actor)
    if actor.user is None:
        raise PermissionDeniedError()
    with transaction.atomic():
        template = _locked(template_id)
        if not template.is_active:
            raise DomainError("template_retired", "The template is retired.")
        # The draft was validated when saved; validate again: rules may have changed.
        fields = schema.clean_fields(template.draft_fields)
        checkpoints = schema.clean_checkpoints(template.draft_checkpoints)
        if not template.has_unpublished_changes and template.versions.exists():
            raise DomainError("nothing_to_publish", "The draft equals the published version.")
        last = template.versions.aggregate(last=Max("number"))["last"] or 0
        version = TemplateVersion.objects.create(
            template=template,
            number=last + 1,
            fields=fields,
            checkpoints=checkpoints,
            published_by=actor.user,
        )
        template.has_unpublished_changes = False
        template.save(update_fields=["has_unpublished_changes", "updated_at"])
        _log(
            actor,
            "request_template.published",
            template,
            version=version.number,
            version_id=str(version.pk),
            field_count=len(fields),
        )
    return version


# --- Who may use a template (D040, Q21) -------------------------------------


def usable_templates(actor: Actor) -> QuerySet[RequestTemplate]:
    """Active, published templates available in a department the actor may
    create tasks for. Read from the database on every call (D020)."""
    scope = access.department_scope(actor, "task.create")
    if not scope:
        return RequestTemplate.objects.none()
    templates = RequestTemplate.objects.filter(
        is_active=True, versions__isnull=False, departments__is_active=True
    )
    if not scope.company:
        templates = templates.filter(departments__in=scope.department_ids)
    return templates.distinct()
