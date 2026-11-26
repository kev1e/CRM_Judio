from django.urls import path

from crm.request_templates.api import views

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
]
