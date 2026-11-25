from django.db import migrations

MANAGER_TASK_GRANTS = [
    "task.archive",
    "task.checkpoints.manage",
    "task.checkpoints.use",
    "task.create",
    "task.deadline",
    "task.delete",
    "task.priority",
    "task.read",
    "task.reassign",
    "task.status",
    "task.update",
]


def forwards(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    RoleGrant = apps.get_model("access", "RoleGrant")
    manager = Role.objects.get(key="department_manager", is_system=True)
    for code in MANAGER_TASK_GRANTS:
        RoleGrant.objects.get_or_create(
            role=manager, permission_code=code, defaults={"scope": "managed_departments"}
        )
    superuser, _ = Role.objects.get_or_create(
        key="superuser",
        defaults={
            "name": "Суперпользователь",
            "description": (
                "Видит задачи всех отделов компании. Только чтение: любое действие "
                "с задачей требует отдельного права."
            ),
            "is_system": True,
        },
    )
    RoleGrant.objects.get_or_create(
        role=superuser, permission_code="task.read", defaults={"scope": "company"}
    )


def backwards(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    apps.get_model("access", "RoleGrant").objects.filter(
        role__key="department_manager", permission_code__in=MANAGER_TASK_GRANTS
    ).delete()
    apps.get_model("access", "UserRole").objects.filter(role__key="superuser").delete()
    Role.objects.filter(key="superuser", is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0004_departments")]

    operations = [migrations.RunPython(forwards, backwards)]
