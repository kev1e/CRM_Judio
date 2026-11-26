from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now

from crm.common.ids import new_id
from crm.projects.models import ProjectInvitation
from crm.tasks.models import Task


class Kind(models.TextChoices):
    TASK_ASSIGNED = "task_assigned", "Task assigned"
    DEADLINE_CHANGED = "deadline_changed", "Deadline changed"
    COMMENT_ADDED = "comment_added", "Comment added"
    STATUS_CHANGED = "status_changed", "Status changed"
    INVITATION_REQUESTED = "invitation_requested", "Project invitation waits for a decision"
    INVITATION_DECIDED = "invitation_decided", "Project invitation decided"
    PROJECT_JOINED = "project_joined", "Added to a project"


class Status(models.TextChoices):
    PENDING = "pending", "Waiting to be sent"
    SENT = "sent", "Sent"
    # Not sent on purpose: the recipient may no longer see the task, left, etc.
    SKIPPED = "skipped", "Not sent"
    FAILED = "failed", "Could not be sent"


class Notification(models.Model):
    """The outbox (Q23): one row per message to one person, written in the same
    transaction as the change it tells about. The text is not stored — it is
    composed when the message is sent, from what the recipient may see then."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=40, choices=Kind.choices)
    # What it is about: a task, or a project invitation — exactly one of them.
    task = models.ForeignKey(
        Task, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    invitation = models.ForeignKey(
        ProjectInvitation, null=True, blank=True, on_delete=models.CASCADE, related_name="+"
    )
    # Who caused it; shown by name in the message.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # A short machine code of why it was skipped or failed. Never a text.
    reason = models.CharField(max_length=40, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(db_default=Now())
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "notifications_notification"
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=Kind.values), name="notifications_notification_kind_known"
            ),
            models.CheckConstraint(
                condition=Q(task__isnull=False, invitation__isnull=True)
                | Q(task__isnull=True, invitation__isnull=False),
                name="notifications_notification_one_subject",
            ),
            models.CheckConstraint(
                condition=Q(status__in=Status.values),
                name="notifications_notification_status_known",
            ),
            models.CheckConstraint(
                condition=Q(status=Status.PENDING, finished_at__isnull=True)
                | (~Q(status=Status.PENDING) & Q(finished_at__isnull=False)),
                name="notifications_notification_finished_consistent",
            ),
        ]
        indexes = [
            models.Index(
                fields=["created_at"],
                name="notif_pending_idx",
                condition=Q(status="pending"),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.recipient_id}:{self.status}"
