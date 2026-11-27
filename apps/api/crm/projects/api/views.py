from typing import Any, cast
from uuid import UUID

from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from crm.access import services as access
from crm.common.actors import Actor
from crm.common.exceptions import DomainError
from crm.identity.api.serializers import ErrorSerializer
from crm.identity.models import User
from crm.organization.models import DepartmentMembership
from crm.projects import services
from crm.projects.api.serializers import (
    CandidateListSerializer,
    DeclineSerializer,
    ParticipantAddedSerializer,
    ParticipantAddSerializer,
    ProjectCreateSerializer,
    ProjectListSerializer,
    ProjectSerializer,
    ProjectUpdateSerializer,
    ZoneMemberSetSerializer,
    ZoneNameSerializer,
)
from crm.projects.models import InvitationState, Project, ProjectInvitation

# Every view needs a session (the API default). Who may see or do what is decided
# by `crm.projects.services`. A project outside the caller's reach is "not found".

_ERRORS = {400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


def _actor(request: Request) -> Actor:
    return Actor.for_user(cast(User, request.user))


def _no_store(body: Any, code: int = status.HTTP_200_OK) -> Response:
    response = Response(body, status=code)
    response["Cache-Control"] = "no-store"
    return response


def _named(pk: UUID, name: str) -> dict[str, Any]:
    return {"id": pk, "name": name}


def _invitation(invitation: ProjectInvitation) -> dict[str, Any]:
    project = invitation.project
    return {
        "id": invitation.pk,
        "project": _named(project.pk, project.name),
        "project_department": _named(project.owning_department_id, project.owning_department.name),
        "user": _named(invitation.user_id, invitation.user.display_name),
        "department": _named(
            invitation.participation_department_id, invitation.participation_department.name
        ),
        "requested_by": _named(invitation.requested_by_id, invitation.requested_by.display_name),
        "created_at": invitation.created_at,
    }


def _project(actor: Actor, project: Project) -> dict[str, Any]:
    manages = services.can_manage(actor, project)
    members = project.members.select_related("user", "participation_department").order_by(
        "user__display_name"
    )
    pending = (
        project.invitations.filter(state=InvitationState.PENDING).select_related(
            "project__owning_department", "user", "participation_department", "requested_by"
        )
        if manages
        else []
    )
    return {
        "id": project.pk,
        "name": project.name,
        "department": _named(project.owning_department_id, project.owning_department.name),
        "is_active": project.is_active,
        "members": [
            {
                "user": _named(m.user_id, m.user.display_name),
                "department": _named(
                    m.participation_department_id, m.participation_department.name
                ),
                "is_active": m.user.is_active,
            }
            for m in members
        ],
        "zones": [
            {
                "id": zone.pk,
                "name": zone.name,
                "members": [
                    {
                        "user": _named(link.member.user_id, link.member.user.display_name),
                        "is_responsible": link.is_responsible,
                    }
                    for link in zone.members.select_related("member__user").order_by(
                        "-is_responsible", "member__user__display_name"
                    )
                ],
            }
            for zone in project.zones.all()
        ],
        "pending_invitations": [_invitation(i) for i in pending],
        "can_manage": manages,
    }


def _visible(actor: Actor, project_id: UUID) -> Project:
    project = (
        services.visible_projects(actor)
        .select_related("owning_department")
        .filter(pk=project_id)
        .first()
    )
    if project is None:
        raise DomainError("project_not_found", "No such project.")
    return project


def _respond(actor: Actor, project_id: UUID, code: int = status.HTTP_200_OK) -> Response:
    return _no_store(_project(actor, _visible(actor, project_id)), code)


class ProjectCollectionView(APIView):
    @extend_schema(
        operation_id="projects_list", responses={200: ProjectListSerializer}, tags=["projects"]
    )
    def get(self, request: Request) -> Response:
        actor = _actor(request)
        projects = services.visible_projects(actor).select_related("owning_department")
        return _no_store(
            {
                "results": [_project(actor, project) for project in projects],
                "invitations_to_decide": [
                    _invitation(i) for i in services.invitations_to_decide(actor)
                ],
                "can_create": bool(access.department_scope(actor, services.MANAGE)),
            }
        )

    @extend_schema(
        operation_id="projects_create",
        request=ProjectCreateSerializer,
        responses={201: ProjectSerializer, **_ERRORS},
        tags=["projects"],
    )
    def post(self, request: Request) -> Response:
        serializer = ProjectCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        project = services.create_project(actor=actor, **serializer.validated_data)
        return _respond(actor, project.pk, status.HTTP_201_CREATED)


class ProjectView(APIView):
    @extend_schema(
        operation_id="projects_update",
        request=ProjectUpdateSerializer,
        responses={200: ProjectSerializer, **_ERRORS},
        tags=["projects"],
    )
    def patch(self, request: Request, project_id: UUID) -> Response:
        serializer = ProjectUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        data = serializer.validated_data
        _visible(actor, project_id)
        if "name" in data:
            services.rename_project(actor=actor, project_id=project_id, name=data["name"])
        if "is_active" in data:
            services.set_project_active(
                actor=actor, project_id=project_id, active=data["is_active"]
            )
        return _respond(actor, project_id)


class ProjectMembersView(APIView):
    @extend_schema(
        operation_id="projects_add_participant",
        request=ParticipantAddSerializer,
        responses={200: ParticipantAddedSerializer, **_ERRORS},
        tags=["projects"],
    )
    def post(self, request: Request, project_id: UUID) -> Response:
        serializer = ParticipantAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        joined = services.add_participant(
            actor=actor, project_id=project_id, **serializer.validated_data
        )
        return _no_store(
            {
                "outcome": "added" if joined.member else "invited",
                "project": _project(actor, _visible(actor, project_id)),
            }
        )


class ProjectMemberView(APIView):
    @extend_schema(
        operation_id="projects_remove_participant",
        responses={200: ProjectSerializer, **_ERRORS},
        tags=["projects"],
    )
    def delete(self, request: Request, project_id: UUID, user_id: UUID) -> Response:
        actor = _actor(request)
        services.remove_participant(actor=actor, project_id=project_id, user_id=user_id)
        return _respond(actor, project_id)


def _invitation_action(name: str) -> type[APIView]:
    class View(APIView):
        @extend_schema(
            operation_id=f"project_invitations_{name}",
            request=DeclineSerializer if name == "decline" else None,
            responses={204: None, **_ERRORS},
            tags=["projects"],
        )
        def post(self, request: Request, invitation_id: UUID) -> Response:
            actor = _actor(request)
            if name == "approve":
                services.approve_invitation(actor=actor, invitation_id=invitation_id)
            elif name == "decline":
                serializer = DeclineSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                services.decline_invitation(
                    actor=actor,
                    invitation_id=invitation_id,
                    reason=serializer.validated_data["reason"],
                )
            else:
                services.cancel_invitation(actor=actor, invitation_id=invitation_id)
            return _no_store(None, status.HTTP_204_NO_CONTENT)

    View.__name__ = f"Invitation{name.title()}View"
    return View


InvitationApproveView = _invitation_action("approve")
InvitationDeclineView = _invitation_action("decline")
InvitationCancelView = _invitation_action("cancel")


class ProjectCandidatesView(APIView):
    """Employees who can be added or invited, with their departments (names only)."""

    @extend_schema(
        operation_id="project_candidates",
        responses={200: CandidateListSerializer, 403: ErrorSerializer},
        tags=["projects"],
    )
    def get(self, request: Request) -> Response:
        people = services.candidates(_actor(request)).prefetch_related(
            Prefetch(
                "department_memberships",
                queryset=DepartmentMembership.objects.filter(department__is_active=True)
                .select_related("department")
                .order_by("department__name"),
            )
        )
        return _no_store(
            {
                "results": [
                    {
                        "id": user.pk,
                        "name": user.display_name,
                        "departments": [
                            _named(m.department_id, m.department.name)
                            for m in user.department_memberships.all()
                        ],
                    }
                    for user in people
                ]
            }
        )


_ZONE_RESPONSES = {200: ProjectSerializer, **_ERRORS}


class ProjectZonesView(APIView):
    @extend_schema(
        operation_id="projects_create_zone",
        request=ZoneNameSerializer,
        responses=_ZONE_RESPONSES,
        tags=["projects"],
    )
    def post(self, request: Request, project_id: UUID) -> Response:
        serializer = ZoneNameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        services.create_zone(
            actor=actor, project_id=project_id, name=serializer.validated_data["name"]
        )
        return _respond(actor, project_id)


class ProjectZoneView(APIView):
    @extend_schema(
        operation_id="projects_rename_zone",
        request=ZoneNameSerializer,
        responses=_ZONE_RESPONSES,
        tags=["projects"],
    )
    def patch(self, request: Request, project_id: UUID, zone_id: UUID) -> Response:
        serializer = ZoneNameSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        services.rename_zone(
            actor=actor,
            project_id=project_id,
            zone_id=zone_id,
            name=serializer.validated_data["name"],
        )
        return _respond(actor, project_id)

    @extend_schema(
        operation_id="projects_delete_zone", responses=_ZONE_RESPONSES, tags=["projects"]
    )
    def delete(self, request: Request, project_id: UUID, zone_id: UUID) -> Response:
        actor = _actor(request)
        services.delete_zone(actor=actor, project_id=project_id, zone_id=zone_id)
        return _respond(actor, project_id)


class ProjectZoneMembersView(APIView):
    @extend_schema(
        operation_id="projects_put_into_zone",
        request=ZoneMemberSetSerializer,
        responses=_ZONE_RESPONSES,
        tags=["projects"],
    )
    def post(self, request: Request, project_id: UUID, zone_id: UUID) -> Response:
        serializer = ZoneMemberSetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = _actor(request)
        services.put_into_zone(
            actor=actor,
            project_id=project_id,
            zone_id=zone_id,
            user_id=serializer.validated_data["user_id"],
            responsible=serializer.validated_data["is_responsible"],
        )
        return _respond(actor, project_id)


class ProjectZoneMemberView(APIView):
    @extend_schema(
        operation_id="projects_take_out_of_zone", responses=_ZONE_RESPONSES, tags=["projects"]
    )
    def delete(self, request: Request, project_id: UUID, zone_id: UUID, user_id: UUID) -> Response:
        actor = _actor(request)
        services.take_out_of_zone(
            actor=actor, project_id=project_id, zone_id=zone_id, user_id=user_id
        )
        return _respond(actor, project_id)
