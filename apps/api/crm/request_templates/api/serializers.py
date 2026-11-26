from typing import Any

from rest_framework import serializers

from crm.tasks.api.serializers import NamedSerializer


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
