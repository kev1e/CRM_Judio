from django.urls import path

from crm.identity.api.user_views import (
    UserBindingCodeView,
    UserCollectionView,
    UserDeactivateView,
    UserReactivateView,
    UserView,
)
from crm.identity.api.views import (
    LoginCompleteView,
    LoginView,
    LogoutView,
    MeView,
    PasswordSetupView,
)

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/login/complete", LoginCompleteView.as_view(), name="auth-login-complete"),
    path("auth/me", MeView.as_view(), name="auth-me"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("auth/password/setup", PasswordSetupView.as_view(), name="auth-password-setup"),
    path("users", UserCollectionView.as_view(), name="users"),
    path("users/<uuid:user_id>", UserView.as_view(), name="user"),
    path(
        "users/<uuid:user_id>/binding-code",
        UserBindingCodeView.as_view(),
        name="user-binding-code",
    ),
    path(
        "users/<uuid:user_id>/deactivate",
        UserDeactivateView.as_view(),
        name="user-deactivate",
    ),
    path(
        "users/<uuid:user_id>/reactivate",
        UserReactivateView.as_view(),
        name="user-reactivate",
    ),
]
