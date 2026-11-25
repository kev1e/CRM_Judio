from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Now

from crm.common.ids import new_id
from crm.organization.models import Department


class Project(models.Model):
    """A group of people working on one thing across departments (D004).

    Belonging to a project shows the project and who takes part in it. It never
    shows a task (D003)."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    name = models.CharField(max_length=150)
    # The department whose managers run the project.
    owning_department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="projects"
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "projects_project"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(Lower("name"), name="projects_project_name_unique"),
            models.CheckConstraint(condition=~Q(name=""), name="projects_project_name_not_empty"),
        ]

    def __str__(self) -> str:
        return self.name


class ProjectMember(models.Model):
    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="project_memberships"
    )
    # The department the person takes part from (Q10).
    participation_department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="+"
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    joined_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "projects_member"
        ordering = ["joined_at", "id"]
        constraints = [
            models.UniqueConstraint(fields=["project", "user"], name="projects_member_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.project_id}:{self.user_id}"


class InvitationState(models.TextChoices):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    CANCELLED = "cancelled"


class ProjectInvitation(models.Model):
    """A request to bring an employee of another department into a project.
    Nothing is granted until the employee's manager approves it (D018, Q10)."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="invitations")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="project_invitations"
    )
    # Chosen by the requester among the employee's departments; its manager decides.
    participation_department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="+"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    state = models.CharField(
        max_length=16, choices=InvitationState.choices, default=InvitationState.PENDING
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "projects_invitation"
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "user"],
                condition=Q(state="pending"),
                name="projects_invitation_one_pending",
            ),
            models.CheckConstraint(
                condition=Q(state__in=[s.value for s in InvitationState]),
                name="projects_invitation_state",
            ),
            models.CheckConstraint(
                condition=(
                    Q(state="pending", decided_by__isnull=True, decided_at__isnull=True)
                    | (~Q(state="pending") & Q(decided_by__isnull=False, decided_at__isnull=False))
                ),
                name="projects_invitation_decision_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"invitation:{self.pk}"
