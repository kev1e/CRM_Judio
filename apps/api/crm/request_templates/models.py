from typing import Any, NoReturn

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Now

from crm.common.ids import new_id
from crm.organization.models import Department


class RequestTemplate(models.Model):
    """A form for requests, owned by the administrator (D009, Q21).

    The template itself holds the *draft* the administrator is editing. People
    only ever use a published `TemplateVersion`."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    name = models.CharField(max_length=150)
    description = models.CharField(max_length=500, blank=True)
    # A retired template takes no new requests; its versions and requests stay.
    is_active = models.BooleanField(default=True)
    draft_fields = models.JSONField(default=list)
    draft_checkpoints = models.JSONField(default=list)
    # Whether the draft differs from the latest published version.
    has_unpublished_changes = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(auto_now=True)
    # Departments in which the template may be used. Empty means nobody (Q21).
    departments = models.ManyToManyField(
        Department, through="TemplateDepartment", related_name="request_templates"
    )

    class Meta:
        db_table = "request_templates_template"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="request_templates_template_name_unique"),
            models.CheckConstraint(
                condition=~Q(name=""), name="request_templates_template_name_not_empty"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class TemplateDepartment(models.Model):
    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    template = models.ForeignKey(RequestTemplate, on_delete=models.CASCADE, related_name="+")
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "request_templates_department"
        constraints = [
            models.UniqueConstraint(
                fields=["template", "department"], name="request_templates_department_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.template_id}:{self.department_id}"


class TemplateVersion(models.Model):
    """A published form. Never changed and never deleted: requests made with it
    keep pointing at exactly this schema (D009). The database refuses UPDATE and
    DELETE on this table."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    template = models.ForeignKey(RequestTemplate, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveIntegerField()
    fields = models.JSONField()
    checkpoints = models.JSONField()
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    published_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "request_templates_version"
        ordering = ["template", "-number"]
        constraints = [
            models.UniqueConstraint(
                fields=["template", "number"], name="request_templates_version_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.template_id}#{self.number}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise TypeError("A published template version is immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise TypeError("A published template version is never deleted.")
