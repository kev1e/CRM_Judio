from typing import Any

from rest_framework import serializers

from crm.tasks.models import Priority, StatusCategory, TaskType

VIEWS = ["mine", "all", "archive", "trash"]


class StatusSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    category = serializers.ChoiceField(choices=StatusCategory.choices)
    position = serializers.IntegerField()
    next_status_ids = serializers.ListField(
        child=serializers.UUIDField(), help_text="Statuses a task may be moved to from this one."
    )
    show_project = serializers.BooleanField(
        help_text="Whether cards in this column show their project."
    )
    group_by_project = serializers.BooleanField(
        help_text="Whether the column is divided into folded lists by project."
    )


class StatusListSerializer(serializers.Serializer[Any]):
    results = StatusSerializer(many=True)


class NamedSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()


class OptionsSerializer(serializers.Serializer[Any]):
    results = NamedSerializer(many=True)


class TaskCardSerializer(serializers.Serializer[Any]):
    """Exactly what a card on the board shows (D005)."""

    id = serializers.UUIDField()
    title = serializers.CharField()
    task_type = serializers.ChoiceField(choices=TaskType.choices)
    priority = serializers.ChoiceField(choices=Priority.choices)
    status_id = serializers.UUIDField()
    due_at = serializers.DateTimeField(allow_null=True)
    department = NamedSerializer()
    project = NamedSerializer(allow_null=True)
    assignee = NamedSerializer()
    checkpoints_done = serializers.IntegerField()
    checkpoints_total = serializers.IntegerField()
    is_completed = serializers.BooleanField()
    is_archived = serializers.BooleanField()
    is_deleted = serializers.BooleanField()
    version = serializers.IntegerField()


class TaskListSerializer(serializers.Serializer[Any]):
    results = TaskCardSerializer(many=True)


class CheckpointSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    text = serializers.CharField()
    is_done = serializers.BooleanField()


class AttachmentSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    name = serializers.CharField()
    byte_size = serializers.IntegerField()
    content_type = serializers.CharField()
    uploader = NamedSerializer()
    created_at = serializers.DateTimeField()


class AttachmentUploadSerializer(serializers.Serializer[Any]):
    file = serializers.FileField(
        help_text="PDF, Word, Excel, an image or a ZIP archive, up to 100 MB."
    )


class CommentSerializer(serializers.Serializer[Any]):
    id = serializers.UUIDField()
    author = NamedSerializer()
    text = serializers.CharField()
    created_at = serializers.DateTimeField()
    edited_at = serializers.DateTimeField(allow_null=True)
    is_own = serializers.BooleanField(help_text="Written by the viewer.")


class CommentWriteSerializer(serializers.Serializer[Any]):
    text = serializers.CharField(max_length=5000, trim_whitespace=True)


class HistoryEntrySerializer(serializers.Serializer[Any]):
    occurred_at = serializers.DateTimeField()
    action = serializers.CharField()
    actor_name = serializers.CharField(allow_blank=True)


class TaskActionsSerializer(serializers.Serializer[Any]):
    edit = serializers.BooleanField()
    status = serializers.BooleanField()
    deadline = serializers.BooleanField()
    checkpoints_use = serializers.BooleanField()
    checkpoints_manage = serializers.BooleanField()
    attach = serializers.BooleanField()
    attachment_delete = serializers.BooleanField()
    comment = serializers.BooleanField()
    comment_delete = serializers.BooleanField()
    priority = serializers.BooleanField()
    project = serializers.BooleanField()
    reassign = serializers.BooleanField()
    archive = serializers.BooleanField()
    delete = serializers.BooleanField()


class TaskDetailSerializer(TaskCardSerializer):
    description = serializers.CharField(allow_blank=True)
    author = NamedSerializer()
    created_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    checkpoints = CheckpointSerializer(many=True)
    attachments = AttachmentSerializer(many=True)
    comments = CommentSerializer(many=True)
    history = HistoryEntrySerializer(many=True)
    actions = TaskActionsSerializer(
        help_text="What the interface may offer. Every operation is checked again by the server."
    )


class TaskCreateSerializer(serializers.Serializer[Any]):
    title = serializers.CharField(max_length=200, trim_whitespace=True)
    description = serializers.CharField(
        max_length=20000, allow_blank=True, required=False, default=""
    )
    department_id = serializers.UUIDField()
    assignee_id = serializers.UUIDField()
    priority = serializers.ChoiceField(choices=Priority.choices, required=False, default="normal")
    due_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    project_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    task_type = serializers.ChoiceField(choices=TaskType.choices, required=False, default="task")


class TaskCreatedSerializer(serializers.Serializer[Any]):
    """A receipt. `task` is present only if the creator may read what they created (Q02)."""

    id = serializers.UUIDField()
    title = serializers.CharField()
    task = TaskDetailSerializer(allow_null=True)


class TaskUpdateSerializer(serializers.Serializer[Any]):
    version = serializers.IntegerField(min_value=1, help_text="The version the client edited.")
    title = serializers.CharField(max_length=200, trim_whitespace=True, required=False)
    description = serializers.CharField(max_length=20000, allow_blank=True, required=False)
    due_at = serializers.DateTimeField(required=False, allow_null=True)
    priority = serializers.ChoiceField(choices=Priority.choices, required=False)
    project_id = serializers.UUIDField(required=False, allow_null=True)
    assignee_id = serializers.UUIDField(required=False)


class TransitionSerializer(serializers.Serializer[Any]):
    status_id = serializers.UUIDField()
    version = serializers.IntegerField(min_value=1, required=False, allow_null=True, default=None)


class CheckpointCreateSerializer(serializers.Serializer[Any]):
    text = serializers.CharField(max_length=200, trim_whitespace=True)


class CheckpointUpdateSerializer(serializers.Serializer[Any]):
    is_done = serializers.BooleanField()


class WorkflowStatusSerializer(StatusSerializer):
    is_active = serializers.BooleanField(help_text="False for a retired status.")
    task_count = serializers.IntegerField(
        help_text="How many tasks have this status now. A number only: no task is shown."
    )


class WorkflowSerializer(serializers.Serializer[Any]):
    results = WorkflowStatusSerializer(many=True)


class WorkflowStatusCreateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=80, trim_whitespace=True)
    category = serializers.ChoiceField(choices=StatusCategory.choices)
    show_project = serializers.BooleanField(required=False, default=True)
    group_by_project = serializers.BooleanField(required=False, default=False)


class WorkflowStatusUpdateSerializer(serializers.Serializer[Any]):
    name = serializers.CharField(max_length=80, trim_whitespace=True, required=False)
    show_project = serializers.BooleanField(required=False)
    group_by_project = serializers.BooleanField(required=False)
    next_status_ids = serializers.ListField(
        child=serializers.UUIDField(), required=False, max_length=100
    )


class WorkflowOrderSerializer(serializers.Serializer[Any]):
    status_ids = serializers.ListField(child=serializers.UUIDField(), max_length=100)


class WorkflowRetireSerializer(serializers.Serializer[Any]):
    replacement_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Required when tasks use the status. Never chosen automatically.",
    )
