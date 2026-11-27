from django.db import migrations
from django.db.models import F

# D042: the administrator role gets every task and project permission company-wide.
# Written out, so the migration does not change when the catalogue grows.
ADDITIONS = [
    "project.invitation.approve",
    "project.manage",
    "task.archive",
    "task.attach",
    "task.attachment.delete",
    "task.checkpoints.manage",
    "task.checkpoints.use",
    "task.comment",
    "task.comment.delete",
    "task.create",
    "task.deadline",
    "task.delete",
    "task.priority",
    "task.project",
    "task.read",
    "task.reassign",
    "task.status",
    "task.update",
]


def _bump(apps, role):
    # Anything issued for the old set of rights becomes stale (D020).
    holders = apps.get_model("access", "UserRole").objects.filter(role=role).values("user_id")
    apps.get_model("identity", "User").objects.filter(pk__in=holders).update(
        permissions_version=F("permissions_version") + 1
    )


def forwards(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    RoleGrant = apps.get_model("access", "RoleGrant")
    administrator = Role.objects.get(key="administrator", is_system=True)
    for code in ADDITIONS:
        RoleGrant.objects.update_or_create(
            role=administrator, permission_code=code, defaults={"scope": "company"}
        )
    _bump(apps, administrator)


def backwards(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    administrator = Role.objects.get(key="administrator", is_system=True)
    apps.get_model("access", "RoleGrant").objects.filter(
        role=administrator, permission_code__in=ADDITIONS
    ).delete()
    _bump(apps, administrator)


class Migration(migrations.Migration):
    dependencies = [
        ("access", "0012_template_manage"),
        ("identity", "0005_user_responsibility"),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
