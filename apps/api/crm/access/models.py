from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Now

from crm.access.permissions import Scope
from crm.common.ids import new_id

ROLE_KEY_REGEX = r"^[a-z][a-z0-9_]{1,62}$"


class Role(models.Model):
    """A named bundle of scoped permissions. A user may hold several roles."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    key = models.CharField(max_length=63, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    # Built-in roles are defined by migrations and cannot be changed or removed at runtime.
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "access_role"
        constraints = [
            models.CheckConstraint(
                condition=Q(key__regex=ROLE_KEY_REGEX), name="access_role_key_format"
            ),
        ]

    def __str__(self) -> str:
        return self.key


class RoleGrant(models.Model):
    """One permission, in one scope, given by a role."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="grants")
    permission_code = models.CharField(max_length=100)
    scope = models.CharField(max_length=32, choices=[(s.value, s.value) for s in Scope])

    class Meta:
        db_table = "access_role_grant"
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission_code"], name="access_role_grant_unique"
            ),
            models.CheckConstraint(
                condition=Q(scope__in=[s.value for s in Scope]), name="access_role_grant_scope"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.role_id}:{self.permission_code}@{self.scope}"


class UserRole(models.Model):
    """A role held by a user."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="role_links"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="user_links")
    granted_at = models.DateTimeField(db_default=Now())
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT, related_name="+"
    )

    class Meta:
        db_table = "access_user_role"
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="access_user_role_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}:{self.role_id}"
