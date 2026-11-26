"""Root URL configuration."""

from django.conf import settings
from django.urls import URLPattern, URLResolver, include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns: list[URLPattern | URLResolver] = [
    path("api/v1/", include("crm.system.api.urls")),
    path("api/v1/", include("crm.identity.api.urls")),
    path("api/v1/", include("crm.organization.api.urls")),
    path("api/v1/", include("crm.tasks.api.urls")),
    path("api/v1/", include("crm.projects.api.urls")),
    path("api/v1/", include("crm.request_templates.api.urls")),
]

if settings.API_SCHEMA_ENABLED:
    urlpatterns.append(path("api/schema", SpectacularAPIView.as_view(), name="schema"))

handler400 = "crm.common.errors.bad_request"
handler403 = "crm.common.errors.permission_denied"
handler404 = "crm.common.errors.not_found"
handler500 = "crm.common.errors.server_error"
