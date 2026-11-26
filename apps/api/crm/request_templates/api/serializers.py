from typing import Any

from rest_framework import serializers

from crm.tasks.api.serializers import NamedSerializer
from crm.tasks.models import Priority


class TemplateVersionSerializer(serializers.Serializer[Any]):
    number = serializers.IntegerField()
    published_at = serializers.DateTimeField()
    published_by = serializers.CharField(help_text="Name of who published it.")
    form_fields = serializers.ListField(child=serializers.DictField())
    checkpoints = serializers.ListField(child=serializers.CharField())


class TemplateSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    is_active = serializers.BooleanField(help_text="False for a retired template.")
    departments = NamedSerializer(many=True)
    draft_fields = serializers.ListField(child=serializers.DictField())
    draft_checkpoints = serializers.ListField(child=serializers.CharField())
    has_unpublished_changes = serializers.BooleanField()
    versions = TemplateVersionSerializer(many=True, help_text="Newest first. Immutable.")


class TemplateListSerializer(serializers.Serializer[Any]):
    results = TemplateSerializer(many=True)


class TemplateCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=150, trim_whitespace=True)
    description = serializers.CharField(
        max_length=500, allow_blank=True, required=False, default="", trim_whitespace=True
    )


class TemplateUpdateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=150, trim_whitespace=True, required=False)
    description = serializers.CharField(
        max_length=500, allow_blank=True, required=False, trim_whitespace=True
    )
    # Checked in depth by `crm.request_templates.schema`.
    draft_fields = serializers.ListField(
        child=serializers.DictField(), required=False, max_length=100
    )
    draft_checkpoints = serializers.ListField(
        child=serializers.CharField(max_length=300), required=False, max_length=100
    )
    department_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=500
    )
    is_active = serializers.BooleanField(required=False)


class RequestFormSerializer(serializers.Serializer[Any]):
    """A form the caller may submit now."""

    id = serializers.UUIDField(help_text="The template.")
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    version = serializers.IntegerField(help_text="Send it back when submitting.")
    form_fields = serializers.ListField(child=serializers.DictField())
    departments = NamedSerializer(
        many=True, help_text="Departments the caller may submit this form for."
    )


class RequestFormListSerializer(serializers.Serializer[Any]):
    results = RequestFormSerializer(many=True)


class RequestPayloadSerializer(serializers.Serializer[Any]):
    """The JSON inside the `payload` part of a submission."""

    template_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1)
    department_id = serializers.UUIDField()
    assignee_id = serializers.UUIDField()
    title = serializers.CharField(max_length=200, trim_whitespace=True)
    priority = serializers.ChoiceField(choices=Priority.choices, default=Priority.NORMAL)
    due_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    # Checked in depth by `crm.request_templates.values`.
    values = serializers.DictField(required=False, default=dict)


class RequestSubmitSerializer(serializers.Serializer[Any]):
    """`multipart/form-data`. Besides `payload`, a file of the field `<key>` is
    sent as a part named `file.<key>`."""

    payload = serializers.CharField(help_text="JSON: see RequestPayload.")


class FormAnswerSerializer(serializers.Serializer[Any]):
    key = serializers.CharField()
    question = serializers.CharField(help_text="The field's label in the form.")
    type = serializers.CharField()
    filled = serializers.BooleanField()
    value = serializers.JSONField(
        allow_null=True,
        help_text="Text, number as text, ISO date, list of options, true/false, "
        "a person's name or a file's name.",
    )
    currency = serializers.CharField(allow_null=True)
    with_time = serializers.BooleanField()
    attachment_id = serializers.UUIDField(
        allow_null=True, help_text="For a file that is still attached."
    )


class SubmittedFormSerializer(serializers.Serializer[Any]):
    template_name = serializers.CharField()
    version = serializers.IntegerField()
    answers = FormAnswerSerializer(many=True)


class TaskFormSerializer(serializers.Serializer[Any]):
    form = SubmittedFormSerializer(
        allow_null=True, help_text="Null for a task made without a form."
    )
