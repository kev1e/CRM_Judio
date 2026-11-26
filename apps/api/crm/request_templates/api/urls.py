from django.urls import path

from crm.request_templates.api import submission_views, views

urlpatterns = [
    path("request-templates", views.TemplateCollectionView.as_view(), name="request-templates"),
    path(
        "request-templates/<uuid:template_id>",
        views.TemplateView.as_view(),
        name="request-template",
    ),
    path(
        "request-templates/<uuid:template_id>/publish",
        views.TemplatePublishView.as_view(),
        name="request-template-publish",
    ),
    path("request-forms", submission_views.RequestFormsView.as_view(), name="request-forms"),
    path("requests", submission_views.RequestsView.as_view(), name="requests"),
    path(
        "tasks/<uuid:task_id>/form",
        submission_views.TaskFormView.as_view(),
        name="task-form",
    ),
]
