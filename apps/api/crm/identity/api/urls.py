from django.urls import path

from crm.identity.api.views import LoginCompleteView, LoginView, LogoutView, MeView

urlpatterns = [
    path("auth/login", LoginView.as_view(), name="auth-login"),
    path("auth/login/complete", LoginCompleteView.as_view(), name="auth-login-complete"),
    path("auth/me", MeView.as_view(), name="auth-me"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
]
