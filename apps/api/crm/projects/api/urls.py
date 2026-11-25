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
