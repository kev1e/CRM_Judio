from django.urls import path

from crm.projects.api import views

urlpatterns = [
    path("projects", views.ProjectCollectionView.as_view(), name="projects"),
    path("projects/<uuid:project_id>", views.ProjectView.as_view(), name="project"),
    path(
        "projects/<uuid:project_id>/members",
        views.ProjectMembersView.as_view(),
        name="project-members",
    ),
    path(
        "projects/<uuid:project_id>/members/<uuid:user_id>",
        views.ProjectMemberView.as_view(),
        name="project-member",
    ),
    path(
        "projects/<uuid:project_id>/zones",
        views.ProjectZonesView.as_view(),
        name="project-zones",
    ),
    path(
        "projects/<uuid:project_id>/zones/<uuid:zone_id>",
        views.ProjectZoneView.as_view(),
        name="project-zone",
    ),
    path(
        "projects/<uuid:project_id>/zones/<uuid:zone_id>/members",
        views.ProjectZoneMembersView.as_view(),
        name="project-zone-members",
    ),
    path(
        "projects/<uuid:project_id>/zones/<uuid:zone_id>/members/<uuid:user_id>",
        views.ProjectZoneMemberView.as_view(),
        name="project-zone-member",
    ),
    path("project-candidates", views.ProjectCandidatesView.as_view(), name="project-candidates"),
    path(
        "project-invitations/<uuid:invitation_id>/approve",
        views.InvitationApproveView.as_view(),
        name="project-invitation-approve",
    ),
    path(
        "project-invitations/<uuid:invitation_id>/decline",
        views.InvitationDeclineView.as_view(),
        name="project-invitation-decline",
    ),
    path(
        "project-invitations/<uuid:invitation_id>/cancel",
        views.InvitationCancelView.as_view(),
        name="project-invitation-cancel",
    ),
]
