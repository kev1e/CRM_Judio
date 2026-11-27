from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now

from crm.common.ids import new_id
from crm.organization.models import Department
from crm.projects.models import Project


class StatusCategory(models.TextChoices):
    NEW = "new"
    ACTIVE = "active"
    # Entering a completed status archives the task at once (D016). Several
    # completed statuses may exist (Q04).
    COMPLETED = "completed"
    # Cancelled is not completed and is never counted as such (Q04).
    CANCELLED = "cancelled"


class TaskStatus(models.Model):
    """A column of the board. Statuses and the moves between them are configuration
    owned by the administrator (D005)."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    name = models.CharField(max_length=80, unique=True)
    category = models.CharField(max_length=16, choices=StatusCategory.choices)
    position = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    # How the board shows this column (the administrator's choice):
    # whether cards here show their project at all, and whether the column is
    # divided into folded lists by project. Presentation only — no rule of
    # access or workflow depends on them.
    show_project = models.BooleanField(default=True)
    group_by_project = models.BooleanField(default=False)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "tasks_status"
        ordering = ["position", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(group_by_project=False) | Q(show_project=True),
                name="tasks_status_grouping_needs_project",
            ),
            models.CheckConstraint(
                condition=Q(category__in=[c.value for c in StatusCategory]),
                name="tasks_status_category",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class StatusTransition(models.Model):
    """An allowed move from one status to another. Anything not listed is refused."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    from_status = models.ForeignKey(TaskStatus, on_delete=models.CASCADE, related_name="moves_out")
    to_status = models.ForeignKey(TaskStatus, on_delete=models.CASCADE, related_name="moves_in")

    class Meta:
        db_table = "tasks_status_transition"
        constraints = [
            models.UniqueConstraint(
                fields=["from_status", "to_status"], name="tasks_transition_unique"
            ),
            models.CheckConstraint(
                condition=~Q(from_status=models.F("to_status")), name="tasks_transition_not_self"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.from_status_id}->{self.to_status_id}"


class TaskType(models.TextChoices):
    TASK = "task"
    # A request is a kind of task, not a separate entity (D006).
    REQUEST = "request"


class Priority(models.TextChoices):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class Task(models.Model):
    """The canonical task. Boards, the archive and the trash are views of this table.

    Exactly one responsible department (D008) and exactly one assignee (Q03).
    Completed, archived, deleted and cancelled are four different facts and are
    stored separately (Q24).
    """

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    task_type = models.CharField(max_length=16, choices=TaskType.choices, default=TaskType.TASK)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=16, choices=Priority.choices, default=Priority.NORMAL)

    responsible_department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="tasks"
    )
    # Optional. A label for grouping: it changes nothing about who sees the task (D003).
    project = models.ForeignKey(
        Project, null=True, blank=True, on_delete=models.PROTECT, related_name="tasks"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="authored_tasks"
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="assigned_tasks"
    )
    # Start of the current assignment (Q18: completion time is measured from here).
    assigned_at = models.DateTimeField()

    status = models.ForeignKey(TaskStatus, on_delete=models.PROTECT, related_name="tasks")
    # The status the task had before it was completed, for reopening (Q05).
    status_before_completion = models.ForeignKey(
        TaskStatus, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    due_at = models.DateTimeField(null=True, blank=True)
    # The first deadline the task ever had; never changed afterwards (Q17).
    original_due_at = models.DateTimeField(null=True, blank=True)

    completed_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    # Incremented by every change; lets a client detect that it edits stale data.
    row_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(db_default=Now())
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tasks_task"
        indexes = [
            models.Index(
                fields=["assignee", "archived_at", "deleted_at"], name="tasks_assignee_idx"
            ),
            models.Index(
                fields=["responsible_department", "archived_at", "deleted_at"],
                name="tasks_department_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(condition=~Q(title=""), name="tasks_task_title_not_empty"),
            models.CheckConstraint(
                condition=Q(priority__in=[p.value for p in Priority]), name="tasks_task_priority"
            ),
            models.CheckConstraint(
                condition=Q(task_type__in=[t.value for t in TaskType]), name="tasks_task_type"
            ),
            # D041 (replaces D016): a completed task stays on the board for a
            # while and is archived later, so completion no longer implies archive.
            models.CheckConstraint(
                condition=(
                    Q(deleted_at__isnull=True, deleted_by__isnull=True)
                    | Q(deleted_at__isnull=False, deleted_by__isnull=False)
                ),
                name="tasks_task_deletion_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"task:{self.pk}"


class Checkpoint(models.Model):
    """A checklist item. Ticking all of them never changes the task's status (D015)."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="checkpoints")
    label = models.CharField(max_length=200)
    position = models.PositiveIntegerField()
    is_done = models.BooleanField(default=False)
    done_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "tasks_checkpoint"
        ordering = ["position", "created_at"]
        constraints = [
            models.CheckConstraint(condition=~Q(label=""), name="tasks_checkpoint_label_not_empty"),
            models.CheckConstraint(
                condition=(
                    Q(is_done=False, done_by__isnull=True, done_at__isnull=True)
                    | Q(is_done=True, done_by__isnull=False, done_at__isnull=False)
                ),
                name="tasks_checkpoint_done_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"checkpoint:{self.pk}"


class Comment(models.Model):
    """A comment on a task. Its author never changes; an edit replaces `body`
    and keeps the previous text as a revision (Q19)."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="task_comments"
    )
    body = models.TextField()
    # 1 for a comment that was never edited.
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(db_default=Now())
    edited_at = models.DateTimeField(null=True, blank=True)
    # D038: a deleted comment is hidden, not erased.
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "tasks_comment"
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(condition=~Q(body=""), name="tasks_comment_body_not_empty"),
            models.CheckConstraint(
                condition=Q(revision=1, edited_at__isnull=True)
                | Q(revision__gt=1, edited_at__isnull=False),
                name="tasks_comment_edit_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    Q(deleted_at__isnull=True, deleted_by__isnull=True)
                    | Q(deleted_at__isnull=False, deleted_by__isnull=False)
                ),
                name="tasks_comment_deletion_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"comment:{self.pk}"


class CommentRevision(models.Model):
    """The text a comment had before an edit. Rows are only ever added."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, related_name="revisions")
    revision = models.PositiveIntegerField()
    body = models.TextField()
    # When this text was written (the comment's creation or the previous edit).
    written_at = models.DateTimeField()
    replaced_at = models.DateTimeField()
    replaced_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "tasks_comment_revision"
        ordering = ["comment", "revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "revision"], name="tasks_comment_revision_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"comment:{self.comment_id}#{self.revision}"


class Attachment(models.Model):
    """A file attached to a task (Q16, D039). The bytes live in the file storage
    under `storage_key`; this row is the only way to reach them, and it is
    reachable only through the task's access rules."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name="attachments")
    uploader = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    storage = models.CharField(max_length=16)
    # Chosen by the CRM; contains nothing typed by a user.
    storage_key = models.CharField(max_length=200, unique=True)
    # For display and for the download's file name only.
    original_name = models.CharField(max_length=200)
    content_type = models.CharField(max_length=100)
    byte_size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(db_default=Now())
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "tasks_attachment"
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(original_name="") & Q(byte_size__gt=0),
                name="tasks_attachment_not_empty",
            ),
            models.CheckConstraint(
                condition=(
                    Q(deleted_at__isnull=True, deleted_by__isnull=True)
                    | Q(deleted_at__isnull=False, deleted_by__isnull=False)
                ),
                name="tasks_attachment_deletion_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"attachment:{self.pk}"
