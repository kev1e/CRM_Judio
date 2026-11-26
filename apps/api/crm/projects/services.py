"""Projects, their participants and cross-department invitations
(S4; D003, D004, D018, Q10, Q29).

* A project belongs to one department; the managers of that department run it
  (`project.manage` in the managed departments).
* A manager adds an employee of a department they manage directly. An employee
  of any other department is only *invited*: nothing is granted until a manager
  of the department the employee takes part from approves
  (`project.invitation.approve`), or a superuser holding that separate
  permission company-wide (Q29).
* The requester names the department of participation; it must be one of the
  employee's current departments, both when asked and when decided (Q10).
* Taking part in a project shows the project and its participants. It never
  shows a task (D003): task access is decided by `crm.tasks.policy` alone.

Who sees a project: its participants, the managers of its department, the
managers of a department somebody takes part from, and holders of a company-wide
`project.manage`.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone

from crm.access import services as access
from crm.audit import services as audit
from crm.common.actors import Actor
from crm.common.exceptions import DomainError, PermissionDeniedError
from crm.identity.models import User
from crm.organization.models import Department, DepartmentMembership
from crm.projects.models import InvitationState, Project, ProjectInvitation, ProjectMember

MANAGE = "project.manage"
APPROVE = "project.invitation.approve"


@dataclass(frozen=True, slots=True)
class Joined:
    """What `add_participant` did: the person is in, or an approval is awaited."""

    member: ProjectMember | None
    invitation: ProjectInvitation | None


def _notifications() -> Any:
    # Imported late: notifications read projects when they are sent.
    from crm.notifications import services

    return services


def _log(actor: Actor, action: str, project: Project, **metadata: object) -> None:
    audit.record(
        actor=actor,
        action=action,
        entity_type="project",
        entity_id=str(project.pk),
        metadata={"department_id": str(project.owning_department_id), **metadata},
    )


def _clean_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name or len(name) > 150:
        raise DomainError("invalid_project_name", "A project needs a name of up to 150 characters.")
    return name


def _user(actor: Actor) -> User:
    if actor.user is None:
        raise PermissionDeniedError()
    return actor.user


# --- Reading ----------------------------------------------------------------


def visible_projects(actor: Actor) -> QuerySet[Project]:
    if actor.user is None:
        return Project.objects.none()
    scope = access.department_scope(actor, MANAGE)
    if scope.company:
        return Project.objects.all()
    reach = Q(members__user=actor.user)
    if scope.department_ids:
        reach |= Q(owning_department_id__in=scope.department_ids)
        reach |= Q(members__participation_department_id__in=scope.department_ids)
    return Project.objects.filter(reach).distinct()


def can_manage(actor: Actor, project: Project) -> bool:
    return access.department_scope(actor, MANAGE).covers(project.owning_department_id)


def _managed(actor: Actor, project_id: UUID) -> Project:
    """Lock a project the actor runs. One they cannot even see does not exist for them."""
    project = (
        Project.objects.select_for_update()
        .filter(pk__in=visible_projects(actor).values("pk"), pk=project_id)
        .first()
    )
    if project is None:
        raise DomainError("project_not_found", "No such project.")
    if not can_manage(actor, project):
        raise PermissionDeniedError()
    return project


def _open(project: Project) -> None:
    if not project.is_active:
        raise DomainError("project_closed", "The project is closed.")


def invitations_to_decide(actor: Actor) -> QuerySet[ProjectInvitation]:
    """Pending invitations the actor may approve or decline."""
    scope = access.department_scope(actor, APPROVE)
    pending = ProjectInvitation.objects.filter(state=InvitationState.PENDING).select_related(
        "project__owning_department", "user", "participation_department", "requested_by"
    )
    if scope.company:
        return pending
    return pending.filter(participation_department_id__in=scope.department_ids)


def candidates(actor: Actor) -> QuerySet[User]:
    """Active employees who can be added or invited: names and departments only.

    PROVISIONAL (docs/OPEN_QUESTIONS.md): somebody who runs a project sees the
    company's list of employees with their departments in order to invite them.
    """
    if not access.department_scope(actor, MANAGE):
        raise PermissionDeniedError()
    return (
        User.objects.filter(is_active=True, department_memberships__department__is_active=True)
        .distinct()
        .order_by("display_name")
    )


# --- Projects ---------------------------------------------------------------


def create_project(*, actor: Actor, name: str, department_id: UUID) -> Project:
    access.require_in_department(actor, MANAGE, department_id)
    creator = _user(actor)
    clean = _clean_name(name)
    if not Department.objects.filter(pk=department_id, is_active=True).exists():
        raise DomainError("department_not_found", "No such open department.")
    try:
        with transaction.atomic():
            project = Project.objects.create(
                name=clean, owning_department_id=department_id, created_by=creator
            )
            _log(actor, "project.created", project)
    except IntegrityError as error:
        raise DomainError(
            "project_name_taken", "A project with this name already exists."
        ) from error
    return project


def rename_project(*, actor: Actor, project_id: UUID, name: str) -> Project:
    clean = _clean_name(name)
    try:
        with transaction.atomic():
            project = _managed(actor, project_id)
            if clean != project.name:
                project.name = clean
                project.save(update_fields=["name"])
                _log(actor, "project.renamed", project)
    except IntegrityError as error:
        raise DomainError(
            "project_name_taken", "A project with this name already exists."
        ) from error
    return project


def set_project_active(*, actor: Actor, project_id: UUID, active: bool) -> Project:
    """Closing a project cancels the invitations that were still waiting."""
    with transaction.atomic():
        project = _managed(actor, project_id)
        if project.is_active == active:
            return project
        project.is_active = active
        project.save(update_fields=["is_active"])
        cancelled = 0
        if not active:
            cancelled = project.invitations.filter(state=InvitationState.PENDING).update(
                state=InvitationState.CANCELLED,
                decided_by=_user(actor),
                decided_at=timezone.now(),
            )
        _log(
            actor,
            "project.reopened" if active else "project.closed",
            project,
            cancelled_invitations=cancelled,
        )
    return project


# --- Participants -----------------------------------------------------------


def _employee_of(user_id: UUID, department_id: UUID) -> User:
    """The active employee, if they belong to that open department right now."""
    membership = (
        DepartmentMembership.objects.select_related("user")
        .filter(
            user_id=user_id,
            department_id=department_id,
            user__is_active=True,
            department__is_active=True,
        )
        .first()
    )
    if membership is None:
        raise DomainError(
            "not_in_department", "The employee does not belong to the chosen department."
        )
    return membership.user


def add_participant(
    *, actor: Actor, project_id: UUID, user_id: UUID, department_id: UUID
) -> Joined:
    """Add an employee of a department the actor manages, or invite one of
    another department. An invitation gives the employee nothing by itself."""
    with transaction.atomic():
        project = _managed(actor, project_id)
        _open(project)
        requester = _user(actor)
        user = _employee_of(user_id, department_id)
        if ProjectMember.objects.filter(project=project, user=user).exists():
            raise DomainError("already_member", "The employee already takes part in the project.")

        if access.department_scope(actor, MANAGE).covers(department_id):
            member = ProjectMember.objects.create(
                project=project,
                user=user,
                participation_department_id=department_id,
                added_by=requester,
            )
            _log(
                actor,
                "project.member_added",
                project,
                user_id=str(user.pk),
                participation_department_id=str(department_id),
                via="direct",
            )
            return Joined(member=member, invitation=None)

        if ProjectInvitation.objects.filter(
            project=project, user=user, state=InvitationState.PENDING
        ).exists():
            raise DomainError("already_invited", "An invitation is already waiting for approval.")
        invitation = ProjectInvitation.objects.create(
            project=project,
            user=user,
            participation_department_id=department_id,
            requested_by=requester,
        )
        _log(
            actor,
            "project.invitation_requested",
            project,
            invitation_id=str(invitation.pk),
            user_id=str(user.pk),
            participation_department_id=str(department_id),
        )
        _notifications().invitation_requested(invitation=invitation, actor=actor)
        return Joined(member=None, invitation=invitation)


def remove_participant(*, actor: Actor, project_id: UUID, user_id: UUID) -> None:
    with transaction.atomic():
        project = _managed(actor, project_id)
        deleted, _ = ProjectMember.objects.filter(project=project, user_id=user_id).delete()
        if not deleted:
            raise DomainError("member_not_found", "The employee does not take part in the project.")
        _log(actor, "project.member_removed", project, user_id=str(user_id))


# --- Invitations ------------------------------------------------------------


def _pending(invitation_id: UUID) -> ProjectInvitation:
    invitation = (
        ProjectInvitation.objects.select_for_update(of=("self",))
        .select_related("project")
        .filter(pk=invitation_id)
        .first()
    )
    if invitation is None:
        raise DomainError("invitation_not_found", "No such invitation.")
    return invitation


def _decide(
    actor: Actor, invitation: ProjectInvitation, state: InvitationState, reason: str = ""
) -> None:
    invitation.state = state
    invitation.decided_by = _user(actor)
    invitation.decided_at = timezone.now()
    invitation.reason = reason.strip()[:500]
    invitation.save(update_fields=["state", "decided_by", "decided_at", "reason"])


def _require_approver(actor: Actor, invitation: ProjectInvitation) -> None:
    # Somebody without the right over this department learns nothing about the invitation.
    if not access.department_scope(actor, APPROVE).covers(invitation.participation_department_id):
        raise DomainError("invitation_not_found", "No such invitation.")
    if invitation.state != InvitationState.PENDING:
        raise DomainError("invitation_decided", "The invitation has already been decided.")


def approve_invitation(*, actor: Actor, invitation_id: UUID) -> ProjectMember:
    """The membership appears here and only here, together with the decision."""
    with transaction.atomic():
        invitation = _pending(invitation_id)
        _require_approver(actor, invitation)
        project = Project.objects.select_for_update().get(pk=invitation.project_id)
        _open(project)
        # Everything is checked again at the moment of the decision (Q10).
        user = _employee_of(invitation.user_id, invitation.participation_department_id)
        _decide(actor, invitation, InvitationState.APPROVED)
        member, _ = ProjectMember.objects.get_or_create(
            project=project,
            user=user,
            defaults={
                "participation_department_id": invitation.participation_department_id,
                "added_by": invitation.requested_by,
            },
        )
        _log(
            actor,
            "project.invitation_approved",
            project,
            invitation_id=str(invitation.pk),
            user_id=str(user.pk),
            participation_department_id=str(invitation.participation_department_id),
        )
        _notifications().invitation_decided(invitation=invitation, actor=actor)
    return member


def decline_invitation(*, actor: Actor, invitation_id: UUID, reason: str = "") -> None:
    with transaction.atomic():
        invitation = _pending(invitation_id)
        _require_approver(actor, invitation)
        _decide(actor, invitation, InvitationState.DECLINED, reason)
        _log(
            actor,
            "project.invitation_declined",
            invitation.project,
            invitation_id=str(invitation.pk),
            user_id=str(invitation.user_id),
        )
        _notifications().invitation_decided(invitation=invitation, actor=actor)


def cancel_invitation(*, actor: Actor, invitation_id: UUID) -> None:
    """The side that asked takes the invitation back."""
    with transaction.atomic():
        invitation = _pending(invitation_id)
        if not can_manage(actor, invitation.project):
            raise DomainError("invitation_not_found", "No such invitation.")
        if invitation.state != InvitationState.PENDING:
            raise DomainError("invitation_decided", "The invitation has already been decided.")
        _decide(actor, invitation, InvitationState.CANCELLED)
        _log(
            actor,
            "project.invitation_cancelled",
            invitation.project,
            invitation_id=str(invitation.pk),
            user_id=str(invitation.user_id),
        )
