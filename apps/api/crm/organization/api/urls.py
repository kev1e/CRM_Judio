from django.urls import path

from crm.organization.api import views

urlpatterns = [
    path("structure/head", views.CompanyHeadView.as_view(), name="structure-head"),
    path("departments", views.DepartmentCollectionView.as_view(), name="departments"),
    path("departments/<uuid:department_id>", views.DepartmentView.as_view(), name="department"),
    path(
        "departments/<uuid:department_id>/members",
        views.DepartmentMembersView.as_view(),
        name="department-members",
    ),
    path(
        "departments/<uuid:department_id>/members/<uuid:user_id>",
        views.DepartmentMemberView.as_view(),
        name="department-member",
    ),
    path(
        "departments/<uuid:department_id>/managers",
        views.DepartmentManagersView.as_view(),
        name="department-managers",
    ),
    path(
        "departments/<uuid:department_id>/managers/<uuid:user_id>",
        views.DepartmentManagerView.as_view(),
        name="department-manager",
    ),
]
