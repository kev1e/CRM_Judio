from django.db import migrations

ADMINISTRATOR_ADDITIONS = ["department.manage", "department.read"]
MANAGER_GRANTS = ["audit.read", "department.read", "user.create", "user.read"]


def forwards(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    RoleGrant = apps.get_model("access", "RoleGrant")
    administrator = Role.objects.get(key="administrator", is_system=True)
    for code in ADMINISTRATOR_ADDITIONS:
        RoleGrant.objects.get_or_create(
            role=administrator, permission_code=code, defaults={"scope": "company"}
        )
    manager, _ = Role.objects.get_or_create(
        key="department_manager",
        defaults={
            "name": "Руководитель отдела",
            "description": (
                "Права руководителя в пределах отделов, которыми он руководит. "
                "Роль выдаётся и снимается автоматически при назначении руководителем."
            ),
            "is_system": True,
        },
    )
    for code in MANAGER_GRANTS:
        RoleGrant.objects.get_or_create(
            role=manager, permission_code=code, defaults={"scope": "managed_departments"}
        )


def backwards(apps, schema_editor):
    Role = apps.get_model("access", "Role")
    RoleGrant = apps.get_model("access", "RoleGrant")
    RoleGrant.objects.filter(
        role__key="administrator", role__is_system=True, permission_code__in=ADMINISTRATOR_ADDITIONS
    ).delete()
    apps.get_model("access", "UserRole").objects.filter(role__key="department_manager").delete()
    Role.objects.filter(key="department_manager", is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [("access", "0003_administrator_user_read")]

    operations = [migrations.RunPython(forwards, backwards)]
