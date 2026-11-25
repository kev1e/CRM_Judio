from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower, Now

from crm.common.ids import new_id


class Department(models.Model):
    """A unit of the company. Every task will have exactly one responsible department."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    name = models.CharField(max_length=150)
    # A closed department keeps its history but takes no new members or managers.
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "organization_department"
        constraints = [
            models.UniqueConstraint(Lower("name"), name="organization_department_name_unique"),
            models.CheckConstraint(
                condition=~Q(name=""), name="organization_department_name_not_empty"
            ),
        ]

    def __str__(self) -> str:
        return self.name


class DepartmentMembership(models.Model):
    """An employee belongs to a department. Any number per employee; exactly one of
    them is the primary one (Q01), chosen by an administrator."""

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="department_memberships"
    )
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="memberships")
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "organization_department_membership"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "department"], name="organization_membership_unique"
            ),
            models.UniqueConstraint(
                fields=["user"],
                condition=Q(is_primary=True),
                name="organization_membership_one_primary_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}@{self.department_id}"


class DepartmentManager(models.Model):
    """An employee manages a department. Managing is separate from belonging: it
    defines the `MANAGED_DEPARTMENTS` scope of the manager's permissions.

    One manager per department is the designated one (Q08): the person who
    receives the open tasks of a deactivated employee of that department.
    """

    id = models.UUIDField(primary_key=True, default=new_id, editable=False)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="managers")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="managed_departments"
    )
    is_designated = models.BooleanField(default=False)
    created_at = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "organization_department_manager"
        constraints = [
            models.UniqueConstraint(
                fields=["department", "user"], name="organization_manager_unique"
            ),
            models.UniqueConstraint(
                fields=["department"],
                condition=Q(is_designated=True),
                name="organization_manager_one_designated_per_department",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} manages {self.department_id}"
